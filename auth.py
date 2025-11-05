from typing import Optional, Dict, Any, Callable, Tuple, TypeVar, Awaitable, List
from dataclasses import dataclass
from functools import wraps, reduce, partial
from aiohttp import web
import hashlib
import secrets
import uuid
from datetime import datetime
from storage import JSONStorage
from config import DATA_DIR
import logging


logger = logging.getLogger(__name__)

# Типы для функционального программирования
T = TypeVar('T')
WebHandler = Callable[[web.Request], Awaitable[web.StreamResponse]]
AuthPredicate = Callable[[Optional['User']], bool]


# Иммутабельные структуры данных
@dataclass(frozen=True)
class User:
    username: str
    role: str
    email: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'username': self.username,
            'role': self.role,
            'email': self.email
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        return cls(
            username=data['username'],
            role=data['role'],
            email=data.get('email')
        )


# Чистые функции для работы с паролями
def hash_password(password: str, salt: str) -> str:
    """Чистая функция для хеширования пароля"""
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode('utf-8'))
    return f"{salt}:{hash_obj.hexdigest()}"


def verify_password(password: str, hashed: str) -> bool:
    """Чистая функция для проверки пароля"""
    try:
        salt, stored_hash = hashed.split(':', 1)
        computed_hash = hash_password(password, salt).split(':')[1]
        return secrets.compare_digest(computed_hash, stored_hash)
    except Exception as e:
        logger.error(f'Error verifying password: {e}')
        return False


# Функции высшего порядка для аутентификации
def extract_token(request: web.Request) -> Optional[str]:
    """Извлекает токен из заголовка или query параметров"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return request.query.get('user')


async def promote_to_admin(username: str) -> bool:
    """Повышает пользователя до администратора"""
    users_result = await users_storage.read_all()
    users = users_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )

    for user in users:
        if user.get('username') == username:
            user['role'] = 'admin'
            write_result = await users_storage.write_all(users)
            return write_result.is_success()
    return False


async def create_admin_user(username: str, password: str) -> bool:
    """Создает администратора (функциональный подход)"""
    users_result = await users_storage.read_all()

    def user_exists(users: List[Dict[str, Any]]) -> bool:
        return any(u.get('username') == username for u in users)

    def add_admin_user(users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return users + [{
            'id': str(uuid.uuid4()),
            'username': username,
            'password_hash': password_hash,
            'role': 'admin',
            'created_at': datetime.now().isoformat()
        }]

    if user_exists(users_result.fold(
            success_func=lambda data: data,
            error_func=lambda e: []
    )):
        return False

    password_hash = await create_hashed_password(password)
    new_users = add_admin_user(users_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    ))

    write_result = await users_storage.write_all(new_users)
    return write_result.fold(
        success_func=lambda _: True,
        error_func=lambda e: False
    )


# Иммутабельное хранилище сессий
class SessionStore:
    def __init__(self):
        self._sessions: Dict[str, User] = {}

    def get_user(self, username: str) -> Optional[User]:
        return self._sessions.get(username)

    def add_user(self, username: str, user_data: Dict[str, Any]) -> 'SessionStore':
        new_store = SessionStore()
        new_store._sessions = {**self._sessions, username: User.from_dict(user_data)}
        return new_store

    def remove_user(self, username: str) -> 'SessionStore':
        new_store = SessionStore()
        new_store._sessions = {k: v for k, v in self._sessions.items() if k != username}
        return new_store


session_store = SessionStore()


@dataclass
class AuthResult:
    """Результат аутентификации с функциональной обработкой"""
    user: Optional[User] = None
    error: Optional[web.HTTPException] = None

    def is_success(self) -> bool:
        return self.user is not None and self.error is None

    def map(self, func: Callable[[User], T]) -> 'AuthResult':
        """Применяет функцию к успешному результату (Functor)"""
        if self.user and not self.error:
            try:
                return AuthResult(user=func(self.user))
            except Exception as e:
                return AuthResult(error=web.HTTPInternalServerError(reason=str(e)))
        return self

    def bind(self, func: Callable[[User], 'AuthResult']) -> 'AuthResult':
        """Цепочка операций (Monadic bind)"""
        if self.user and not self.error:
            return func(self.user)
        return self

    def fold(self, success_func: Callable[[User], T], error_func: Callable[[web.HTTPException], T]) -> T:
        """Разворачивает результат (Catamorphism)"""
        if self.user and not self.error:
            return success_func(self.user)
        return error_func(self.error) if self.error else error_func(web.HTTPUnauthorized())


def compose_middleware(*middlewares: Callable) -> Callable:
    """Композиция middleware функций"""

    def compose_two(f: Callable, g: Callable) -> Callable:
        return lambda x: f(g(x))

    return reduce(compose_two, middlewares)


def create_auth_decorator(*predicates: AuthPredicate) -> Callable:
    """Создает декоратор аутентификации с композицией предикатов"""

    def decorator(handler: WebHandler) -> WebHandler:
        @wraps(handler)
        async def wrapper(request: web.Request) -> web.StreamResponse:
            auth_result = await (
                AuthResult()
                .bind(lambda _: get_current_user(request))
                .bind(lambda user: check_predicates(user, predicates))
            )

            return await auth_result.fold(
                success_func=lambda user: handler(request),
                error_func=lambda error: raise_error(error)
            )

        return wrapper

    return decorator


async def get_current_user(request: web.Request) -> AuthResult:
    """Получение текущего пользователя с функциональной обработкой"""
    token = extract_token(request)
    if not token:
        return AuthResult(error=web.HTTPUnauthorized())

    user = session_store.get_user(token)
    if user:
        return AuthResult(user=user)

    try:
        users_result = await users_storage.read_all()
        users = users_result.fold(
            success_func=lambda data: data,
            error_func=lambda e: []
        )
        user_data = next((u for u in users if u.get('username') == token), None)
        if user_data:
            user_obj = User.from_dict(user_data)
            global session_store
            session_store = session_store.add_user(token, user_data)
            return AuthResult(user=user_obj)
    except Exception as e:
        logger.error(f"Error loading user: {e}")

    return AuthResult(error=web.HTTPUnauthorized())


def check_predicates(user: Optional[User], predicates: Tuple[AuthPredicate, ...]) -> AuthResult:
    """Проверка композиции предикатов"""
    if all(predicate(user) for predicate in predicates):
        return AuthResult(user=user)
    return AuthResult(error=web.HTTPForbidden())


async def raise_error(error: web.HTTPException) -> None:
    """Поднимает исключение (эффект)"""
    raise error


def requires_html_redirect(request: web.Request) -> bool:
    """Предикат для проверки необходимости HTML редиректа"""
    return (request.headers.get('Accept', '').find('text/html') >= 0
            and request.method == 'GET')


def is_authenticated(user: Optional[User]) -> bool:
    return user is not None


def has_role(role: str) -> AuthPredicate:
    return lambda user: user is not None and user.role == role


require_login = create_auth_decorator(is_authenticated)
require_admin = create_auth_decorator(is_authenticated, has_role('admin'))
require_moderator = create_auth_decorator(is_authenticated, has_role('moderator'))


def create_web_auth_decorator(*predicates: AuthPredicate) -> Callable:
    """Версия с обработкой веб-редиректов"""

    def decorator(handler: WebHandler) -> WebHandler:
        @wraps(handler)
        async def wrapper(request: web.Request) -> web.StreamResponse:
            auth_result = await get_current_user(request)

            def handle_auth_failure(error: web.HTTPException) -> web.HTTPException:
                """Обработка неудачной аутентификации с редиректами"""
                if (isinstance(error, web.HTTPUnauthorized) and
                        requires_html_redirect(request)):
                    return web.HTTPFound('/login')
                return error

            checked_result = auth_result.bind(
                lambda user: check_predicates(user, predicates)
            )

            final_error = checked_result.fold(
                success_func=lambda user: None,
                error_func=handle_auth_failure
            )

            if final_error:
                raise final_error

            return await handler(request)

        return wrapper

    return decorator


async def create_hashed_password(password: str) -> str:
    """Генерация хешированного пароля с солью"""
    salt = secrets.token_hex(16)
    return hash_password(password, salt)


class AuthHandlers:
    @require_login
    async def protected_handler(self, request: web.Request) -> web.Response:
        user_result = await get_current_user(request)
        return web.json_response({
            'message': 'Access granted',
            'user': user_result.fold(
                success_func=lambda u: u.to_dict(),
                error_func=lambda e: {'error': str(e)}
            )
        })

    @require_admin
    async def admin_handler(self, request: web.Request) -> web.Response:
        return web.json_response({'message': 'Admin access granted'})

    @create_web_auth_decorator(is_authenticated, has_role('moderator'))
    async def moderator_handler(self, request: web.Request) -> web.Response:
        return web.json_response({'message': 'Moderator access granted'})


def pipeline(*functions: Callable) -> Callable:
    """Создает pipeline из функций"""
    return reduce(lambda f, g: lambda x: g(f(x)), functions)


def maybe(value: Optional[T]) -> 'Maybe':
    """Maybe monad для обработки optional значений"""
    return Maybe(value)


class Maybe:
    """Упрощенная Maybe монада"""

    def __init__(self, value: Optional[T]):
        self.value = value

    def map(self, func: Callable[[T], U]) -> 'Maybe':
        if self.value is not None:
            try:
                return Maybe(func(self.value))
            except Exception:

                return Maybe(None)
        return self

    def bind(self, func: Callable[[T], 'Maybe']) -> 'Maybe':
        if self.value is not None:
            return func(self.value)
        return self

    def or_else(self, default: T) -> T:
        return self.value if self.value is not None else default


users_storage = JSONStorage(f"{DATA_DIR}/users.json")
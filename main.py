import aiohttp
from aiohttp import web, web_request
from aiohttp.web import Request, Response
import json
from typing import Dict, Any, List, Optional, Callable, Tuple, TypeVar, Awaitable
from dataclasses import dataclass
from functools import wraps, reduce, partial
from datetime import datetime
import uuid
import logging

from models import Resume, AnalysisResult, JobDescription
from storage import JSONStorage
from rag_analyzer import RAGAnalyzer
from json_utils import safe_json_response
from config import DATA_DIR, RESUMES_FILE, ANALYSES_FILE, HOST, PORT
from auth import users_storage, get_current_user, require_login, create_admin_user

logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U')
Handler = Callable[[Request], Awaitable[Response]]
Middleware = Callable[[Request, Handler], Awaitable[Response]]


@with_error_handling
async def debug_analysis(request: Request) -> Response:
    """Диагностический эндпоинт для отладки анализа"""
    logger.info("=== DEBUG ANALYSIS START ===")

    resumes_result = await resume_storage.read_all()
    jobs_result = await job_storage.read_all()
    analyses_result = await analysis_storage.read_all()

    resumes = resumes_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )
    jobs = jobs_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )
    analyses = analyses_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )

    response_data = {
        "status": "success",
        "resumes_count": len(resumes),
        "jobs_count": len(jobs),
        "analyses_count": len(analyses),
        "resumes": [r.get('name', 'Unknown') for r in resumes[:5]],  # Только первые 5
        "jobs": [j.get('title', 'Unknown') for j in jobs[:5]],
        "analyses": [f"Resume: {a.get('resume_id', 'Unknown')} -> {a.get('job_match_percentage', 0)}%" for a in
                     analyses[:5]]
    }

    return safe_json_response(response_data)


def convert_analysis_to_dict(analysis: AnalysisResult) -> Dict[str, Any]:
    """Конвертирует AnalysisResult в словарь, готовый для JSON"""
    if hasattr(analysis, 'json_serializable_dict'):
        return analysis.json_serializable_dict()

    analysis_dict = {
        'id': analysis.id,
        'resume_id': analysis.resume_id,
        'relevance_score': analysis.relevance_score,
        'strengths': analysis.strengths,
        'weaknesses': analysis.weaknesses,
        'recommendations': analysis.recommendations,
        'job_match_percentage': analysis.job_match_percentage,
        'analysis_text': analysis.analysis_text,
        'created_at': analysis.created_at.isoformat() if analysis.created_at else None
    }
    return analysis_dict

@with_error_handling
async def analyze_resume(request: Request) -> Response:
    """API: Анализ релевантности резюме"""
    try:
        data = await request.json()
        resume_id = data.get('resume_id')
        job_id = data.get('job_id')

        logger.info(f"Analysis request: resume_id={resume_id}, job_id={job_id}")

        if not resume_id or not job_id:
            logger.warning("Missing resume_id or job_id in analysis request")
            return safe_json_response({"error": "Требуются resume_id и job_id"}, status=400)

        resume_result = await resume_storage.get_item(resume_id)
        job_result = await job_storage.get_item(job_id)

        resume_data = resume_result.fold(
            success_func=lambda data: data,
            error_func=lambda e: None
        )
        job_data = job_result.fold(
            success_func=lambda data: data,
            error_func=lambda e: None
        )

        if not resume_data:
            logger.error(f"Resume not found: {resume_id}")
            return safe_json_response({"error": f"Резюме {resume_id} не найдено"}, status=404)

        if not job_data:
            logger.error(f"Job not found: {job_id}")
            return safe_json_response({"error": f"Вакансия {job_id} не найдена"}, status=404)

        logger.info(f"Found resume: {resume_data.get('name')}, job: {job_data.get('title')}")

        try:
            resume = Resume(**resume_data)
            job = JobDescription(**job_data)
            logger.debug("Models created successfully")
        except Exception as e:
            logger.error(f"Model creation failed: {e}")
            return safe_json_response({"error": f"Ошибка создания моделей: {e}"}, status=400)

        logger.info("Starting RAG analysis...")
        analysis = await rag_analyzer.analyze_resume_relevance(resume, job)
        logger.info(f"RAG analysis completed: {analysis.relevance_score}")

        analysis_dict = convert_analysis_to_dict(analysis)

        save_result = await analysis_storage.add_item(analysis_dict)

        return save_result.fold(
            success_func=lambda analysis_id: safe_json_response({
                **analysis_dict,
                "analysis_id": analysis_id,
                "message": "Анализ выполнен успешно"
            }),
            error_func=lambda e: safe_json_response({
                "error": f"Ошибка сохранения анализа: {e}",
                "analysis": analysis_dict
            }, status=500)
        )

    except Exception as e:
        logger.error(f"Analysis endpoint error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return safe_json_response({"error": f"Внутренняя ошибка сервера: {e}"}, status=500)



@dataclass(frozen=True)
class HttpContext:
    """Иммутабельный контекст HTTP запроса"""
    request: Request
    user: Optional[Dict[str, Any]] = None
    data: Optional[Any] = None
    params: Optional[Dict[str, Any]] = None


@dataclass
class HttpResult:
    """Монадический результат HTTP обработки"""
    response: Optional[Response] = None
    context: Optional[HttpContext] = None
    error: Optional[Exception] = None

    def is_success(self) -> bool:
        return self.response is not None and self.error is None

    def map(self, func: Callable[[Response], T]) -> 'HttpResult':
        """Functor map для преобразования ответа"""
        if self.response and not self.error:
            try:
                return HttpResult(response=func(self.response), context=self.context)
            except Exception as e:
                return HttpResult(error=e, context=self.context)
        return self

    def bind(self, func: Callable[[Response], 'HttpResult']) -> 'HttpResult':
        """Monadic bind для цепочек обработки"""
        if self.response and not self.error:
            return func(self.response)
        return self

    def fold(self, success_func: Callable[[Response], T], error_func: Callable[[Exception], T]) -> T:
        """Catamorphism для извлечения результата"""
        if self.response and not self.error:
            return success_func(self.response)
        return error_func(self.error) if self.error else error_func(Exception("Unknown error"))


resume_storage = JSONStorage(f"{DATA_DIR}/{RESUMES_FILE}")
analysis_storage = JSONStorage(f"{DATA_DIR}/{ANALYSES_FILE}")
job_storage = JSONStorage(f"{DATA_DIR}/jobs.json")
logs_storage = JSONStorage(f"{DATA_DIR}/logs.json")

rag_analyzer = RAGAnalyzer()


def generate_nav(user: Optional[Dict[str, Any]]) -> str:
    """Чистая функция генерации навигации"""
    username = user['username'] if user else 'Гость'
    auth_link = '<a href="/logout">Выйти</a>' if user else '<a href="/login">Войти</a>'

    return f"""
    <div class="nav">
        <a href="/">Главная</a>
        <a href="/resumes">Резюме</a>
        <a href="/jobs">Вакансии</a>
        <a href="/analyses">Анализы</a>
        <a href="/admin">Админ</a>
        <span class="badge">{username}</span>
        {auth_link}
    </div>
    """


def base_html_template(title: str, content: str, user: Optional[Dict[str, Any]] = None) -> str:
    """Чистая функция базового HTML шаблона"""
    nav = generate_nav(user)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta charset="utf-8">
        <style>
            :root {{ --bg:#f5f5f7; --card:#ffffff; --text:#1d1d1f; --muted:#6e6e73; --accent:#0071e3; --radius:18px; --shadow:0 8px 30px rgba(0,0,0,0.06); }}
            * {{ box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif; margin: 0; background: var(--bg); color: var(--text); }}
            .container {{ max-width: 1024px; margin: 0 auto; padding: 40px 24px; }}
            .nav {{ display: flex; gap: 16px; align-items: center; margin: 12px 0 24px; }}
            .nav a {{ text-decoration: none; color: var(--text); padding: 8px 12px; border-radius: 12px; }}
            .nav a:hover {{ background: #e8e8ed; }}
            .badge {{ margin-left: auto; color: var(--muted); font-size: 14px; }}
            .hero {{ background: linear-gradient(180deg, #fff, #fafafa); border-radius: var(--radius); box-shadow: var(--shadow); padding: 32px; }}
            h1 {{ font-size: 36px; margin: 0 0 12px; letter-spacing: -0.02em; }}
            p {{ color: var(--muted); font-size: 18px; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-top: 24px; }}
            .card {{ background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px; }}
            .card h3 {{ margin-top: 0; }}
            .button {{ background: var(--accent); color: #fff; padding: 10px 16px; border: none; border-radius: 999px; cursor: pointer; }}
            .button:hover {{ filter: brightness(0.95); }}
        </style>
    </head>
    <body>
        <div class="container">
            {nav}
            {content}
        </div>
    </body>
    </html>
    """


"""Декоратор для автоматического преобразования в JSON ответ с безопасной сериализацией"""
def with_json_response(func: Callable) -> Callable:
    """Декоратор для автоматического преобразования в JSON ответ с безопасной сериализацией"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            if isinstance(result, Response):
                return result
            return safe_json_response(result)
        except Exception as e:
            logger.error(f"JSON response error: {e}")
            return safe_json_response({"error": str(e)}, status=500)

    return wrapper


def with_error_handling(func: Callable) -> Callable:
    """Декоратор для обработки ошибок"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except web.HTTPException:
            raise
        except Exception as e:
            logger.error(f"Handler error: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    return wrapper


def require_fields(*required_fields: str) -> Callable:
    """Декоратор для проверки обязательных полей"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(request: Request):
            try:
                data = await request.json()
                missing = [field for field in required_fields if field not in data]
                if missing:
                    return web.json_response(
                        {"error": f"Missing required fields: {', '.join(missing)}"},
                        status=400
                    )
                return await func(request)
            except json.JSONDecodeError:
                return web.json_response({"error": "Invalid JSON"}, status=400)

        return wrapper

    return decorator


# Композиция middleware
def compose_middleware(*middlewares: Middleware) -> Middleware:
    """Композиция middleware функций"""

    def apply_middleware(handler: Handler, middleware: Middleware) -> Handler:
        return lambda request: middleware(request, handler)

    return reduce(apply_middleware, middlewares, lambda request: handler(request))


# Композиция функций
def compose(*functions: Callable) -> Callable:
    """Композиция функций"""
    return reduce(lambda f, g: lambda x: g(f(x)), functions)


# Функциональные обработчики страниц
async def index(request: Request) -> Response:
    """Главная страница"""
    user = await get_current_user(request)

    content = """
    <div class="hero">
        <h1>Система анализа релевантности резюме</h1>
        <p>Анализируйте соответствие кандидатов вакансиям с помощью RAG. Хранение — только JSON.</p>
        <div class="grid">
            <div class="card"><h3>Резюме</h3><p>Создавайте и импортируйте резюме из hh.ru.</p></div>
            <div class="card"><h3>Вакансии</h3><p>Добавляйте описания и требования.</p></div>
            <div class="card"><h3>Анализ</h3><p>Автоматический разбор релевантности.</p></div>
        </div>
    </div>
    """

    html = base_html_template("Система анализа резюме", content, user)
    return web.Response(text=html, content_type='text/html')


async def resumes_page(request: Request) -> Response:
    """Страница управления резюме"""
    user = await get_current_user(request)
    resumes_result = await resume_storage.read_all()

    resumes = resumes_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )

    form_html = """
    <h2>Добавить новое резюме</h2>
    <form id="resumeForm">
        <div class="form-group">
            <label>Имя кандидата:</label>
            <input type="text" name="name" required>
        </div>
        <div class="form-group">
            <label>Позиция:</label>
            <input type="text" name="position" required>
        </div>
        <div class="form-group">
            <label>Опыт работы (лет):</label>
            <input type="number" name="experience" required>
        </div>
        <div class="form-group">
            <label>Навыки (через запятую):</label>
            <input type="text" name="skills" placeholder="Python, JavaScript, SQL">
        </div>
        <div class="form-group">
            <label>Образование:</label>
            <input type="text" name="education" required>
        </div>
        <div class="form-group">
            <label>Языки (через запятую):</label>
            <input type="text" name="languages" placeholder="Русский, Английский">
        </div>
        <div class="form-group">
            <label>Email:</label>
            <input type="email" name="email" required>
        </div>
        <div class="form-group">
            <label>Телефон:</label>
            <input type="text" name="phone" required>
        </div>
        <button type="submit">Добавить резюме</button>
    </form>

    <h2>Импорт резюме с hh.ru</h2>
    <p>Вставьте JSON из API hh.ru (поле resume или аналогичный объект). Мы преобразуем его к внутреннему формату.</p>
    <div class="form-group">
        <label>HH JSON:</label>
        <textarea id="hhJson" rows="10" placeholder="{'first_name': 'Иван', ...}"></textarea>
    </div>
    <button id="importHh">Импортировать из hh.ru</button>
    """

    resumes_list = "".join([
        f"""
        <div class="resume-item">
            <h3>{resume.get('name', 'N/A')} - {resume.get('position', 'N/A')}</h3>
            <p><strong>Опыт:</strong> {resume.get('experience', 0)} лет</p>
            <p><strong>Навыки:</strong> <span class="skills">{', '.join(resume.get('skills', []))}</span></p>
            <p><strong>Образование:</strong> {resume.get('education', 'N/A')}</p>
            <p><strong>Языки:</strong> {', '.join(resume.get('languages', []))}</p>
            <p><strong>Контакты:</strong> {resume.get('contact_info', {}).get('email', 'N/A')}, {resume.get('contact_info', {}).get('phone', 'N/A')}</p>
            <p><strong>Создано:</strong> {resume.get('created_at', 'N/A')}</p>
        </div>
        """ for resume in resumes
    ])

    content = f"""
    <h1>Управление резюме</h1>
    {form_html}
    <h2>Список резюме ({len(resumes)})</h2>
    {resumes_list}
    """

    html = base_html_template("Управление резюме", content, user)
    return web.Response(text=html, content_type='text/html')


@require_admin_fp
async def admin_page(request: Request) -> Response:
    """Страница администратора с функциональным подходом"""
    users_result = await users_storage.read_all()
    logs_result = await logs_storage.read_all()

    def render_users_table(users: List[Dict[str, Any]]) -> str:
        return "".join([
            f"<tr><td>{u.get('username')}</td><td>{u.get('role')}</td><td>{u.get('created_at')}</td></tr>"
            for u in users
        ])

    def render_logs_table(logs: List[Dict[str, Any]]) -> str:
        return "".join([
            f"<tr><td>{l.get('ts')}</td><td>{l.get('method')}</td><td>{l.get('path')}</td><td>{l.get('status')}</td><td>{l.get('user')}</td><td>{l.get('ip')}</td><td>{l.get('duration_ms')}</td></tr>"
            for l in logs[-200:]
        ])

    users_html = users_result.fold(
        success_func=render_users_table,
        error_func=lambda e: f"<tr><td colspan='3'>Ошибка загрузки: {e}</td></tr>"
    )

    logs_html = logs_result.fold(
        success_func=render_logs_table,
        error_func=lambda e: f"<tr><td colspan='7'>Ошибка загрузки: {e}</td></tr>"
    )

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset='utf-8'>
        <title>Админ панель</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, Arial; background:#f5f5f7; margin:0; }}
            .container {{ max-width: 1100px; margin: 0 auto; padding: 32px; }}
            .card {{ background:#fff; border-radius:18px; box-shadow:0 8px 30px rgba(0,0,0,0.06); padding:20px; margin:12px 0; }}
            table {{ width:100%; border-collapse: collapse; }}
            th, td {{ text-align:left; padding:8px 6px; border-bottom:1px solid #eee; font-size:14px; }}
        </style>
    </head>
    <body>
        <div class='container'>
            <h2>Админ панель</h2>
            <div class='card'>
                <h3>Пользователи</h3>
                <table>
                    <thead><tr><th>Логин</th><th>Роль</th><th>Создан</th></tr></thead>
                    <tbody>{users_html}</tbody>
                </table>
            </div>
            <div class='card'>
                <h3>Логи</h3>
                <table>
                    <thead><tr><th>Время</th><th>Метод</th><th>Путь</th><th>Статус</th><th>Пользователь</th><th>IP</th><th>Длительность, мс</th></tr></thead>
                    <tbody>{logs_html}</tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')


async def create_admin_post(request: Request) -> Response:
    """Обработка создания администратора"""
    data = await request.post()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return web.Response(text="Укажите логин и пароль", status=400)

    success = await create_admin_user(username, password)

    if success:
        return web.Response(text="""
        <!DOCTYPE html>
        <html>
        <head><meta charset='utf-8'><title>Успех</title></head>
        <body>
            <div style='max-width:380px; margin:80px auto; text-align:center;'>
                <h2>Администратор создан!</h2>
                <p>Теперь вы можете <a href='/login'>войти в систему</a> с правами администратора.</p>
            </div>
        </body>
        </html>
        """, content_type='text/html')
    else:
        return web.Response(text="Ошибка при создании администратора", status=500)


@with_error_handling
@with_json_response
@require_fields('name', 'position', 'experience')
async def create_resume(request: Request) -> Dict[str, Any]:
    """API: Создание резюме"""
    data = await request.json()
    result = await resume_storage.add_item(data)

    return result.fold(
        success_func=lambda resume_id: {"id": resume_id, "message": "Резюме создано успешно"},
        error_func=lambda e: {"error": str(e)}
    )


@with_error_handling
@with_json_response
async def get_resumes(request: Request) -> List[Dict[str, Any]]:
    """API: Получение всех резюме"""
    result = await resume_storage.read_all()

    return result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )


class Maybe:
    """Maybe монада для безопасной обработки значений"""

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


def safe_get(data: Dict[str, Any], *keys: str) -> Maybe:
    """Безопасное получение значения из словаря"""
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return Maybe(None)
    return Maybe(current)


def require_admin_fp(handler: Callable) -> Callable:
    """Функциональная версия проверки администратора"""

    @wraps(handler)
    async def wrapper(request: Request) -> Response:
        user = await get_current_user(request)

        is_admin = (
                user is not None and
                user.get('role') == 'admin'
        )

        if not is_admin:
            users = await users_storage.read_all()
            has_any_admin = any(u.get('role') == 'admin' for u in users)

            if not has_any_admin:
                raise web.HTTPFound('/create-admin')
            else:
                raise web.HTTPForbidden()

        return await handler(request)

    return wrapper

def map_hh_to_internal_fp(hh_data: Dict[str, Any]) -> Dict[str, Any]:
    """Функциональная версия преобразования HH JSON"""
    full_name = Maybe(hh_data).bind(
        lambda data: safe_get(data, 'first_name').map(
            lambda first: f"{first} {safe_get(data, 'last_name').or_else('')}".strip()
        )
    ).or_else(safe_get(hh_data, 'title').or_else('Кандидат hh.ru'))

    position = Maybe(hh_data).bind(
        lambda data: safe_get(data, 'title').or_else(
            safe_get(data, 'position').or_else('Специалист')
        )
    ).or_else('Специалист')

    experience_years = Maybe(hh_data).bind(
        lambda data: safe_get(data, 'experience', 'total', 'months').map(
            lambda months: max(0, round(months / 12))
        ).or_else(
            safe_get(data, 'experience', 'total').map(
                lambda total: max(0, round(total / 12))
            )
        )
    ).or_else(0)

    skills = Maybe(hh_data).bind(
        lambda data: safe_get(data, 'key_skills').or_else(safe_get(data, 'skills'))
    ).map(
        lambda skills_list: [
            skill.get('name') if isinstance(skill, dict) else skill
            for skill in skills_list if skill
        ] if isinstance(skills_list, list) else []
    ).or_else([])

    education = Maybe(hh_data).bind(
        lambda data: safe_get(data, 'education', 'level', 'name')
    ).or_else('Не указано')

    languages = Maybe(hh_data).bind(
        lambda data: safe_get(data, 'language').or_else(safe_get(data, 'languages'))
    ).map(
        lambda langs: [
            f"{lang.get('name', lang.get('id', ''))} ({lang.get('level', {}).get('name', '')})".strip().rstrip(
                '()').strip()
            for lang in langs if isinstance(lang, dict)
        ] if isinstance(langs, list) else []
    ).or_else([])

    # Контакты
    email = Maybe(hh_data).bind(
        lambda data: safe_get(data, 'contact', 'email').or_else(safe_get(data, 'email'))
    ).or_else('')

    phone = Maybe(hh_data).bind(
        lambda data: safe_get(data, 'contact', 'phone', 'formatted').or_else(
            safe_get(data, 'contact', 'phone', 'number')
        ).or_else(
            safe_get(data, 'phones', 0, 'formatted').or_else(
                safe_get(data, 'phones', 0, 'number')
            ).or_else(safe_get(data, 'phones', 0))
        )
    ).or_else('')

    return {
        'name': full_name,
        'position': position,
        'experience': experience_years,
        'skills': skills,
        'education': education,
        'languages': languages,
        'contact_info': {
            'email': email,
            'phone': phone
        }
    }


@with_error_handling
@with_json_response
async def import_hh_resume(request: Request) -> Dict[str, Any]:
    """API: Импорт резюме из hh.ru JSON"""
    hh_json = await request.json()
    mapped_data = map_hh_to_internal_fp(hh_json)
    result = await resume_storage.add_item(mapped_data)

    return result.fold(
        success_func=lambda resume_id: {"id": resume_id, "message": "Импортировано из hh.ru"},
        error_func=lambda e: {"error": str(e)}
    )


async def logging_middleware_fp(request: Request, handler: Handler) -> Response:
    """Функциональный middleware для логирования"""
    start_time = datetime.now()
    user = await get_current_user(request)

    try:
        response = await handler(request)
        status = response.status
        return response
    except Exception as e:
        status = 500
        raise e
    finally:
        duration = (datetime.now() - start_time).total_seconds() * 1000

        log_entry = {
            'ts': datetime.now().isoformat(),
            'method': request.method,
            'path': request.path,
            'status': status,
            'user': user.get('username') if user else None,
            'ip': request.remote,
            'duration_ms': int(duration),
        }

        await logs_storage.add_item(log_entry)


@with_error_handling
@with_json_response
async def get_jobs(request: Request) -> List[Dict[str, Any]]:
    """API: Получение всех вакансий"""
    result = await job_storage.read_all()

    return result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )


@with_error_handling
@with_json_response
async def get_analyses(request: Request) -> List[Dict[str, Any]]:
    """API: Получение всех анализов"""
    result = await analysis_storage.read_all()

    return result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )


@with_error_handling
@with_json_response
async def create_job(request: Request) -> Dict[str, Any]:
    """API: Создание вакансии"""
    data = await request.json()
    result = await job_storage.add_item(data)

    return result.fold(
        success_func=lambda job_id: {"id": job_id, "message": "Вакансия создана успешно"},
        error_func=lambda e: {"error": str(e)}
    )


async def jobs_page(request: Request) -> Response:
    """Страница управления вакансиями"""
    user = await get_current_user(request)
    jobs_result = await job_storage.read_all()

    jobs = jobs_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )

    form_html = """
    <h2>Добавить новую вакансию</h2>
    <form id="jobForm">
        <div class="form-group">
            <label>Название позиции:</label>
            <input type="text" name="title" required>
        </div>
        <div class="form-group">
            <label>Требования (через запятую):</label>
            <input type="text" name="requirements" placeholder="Опыт работы, Образование">
        </div>
        <div class="form-group">
            <label>Обязанности (через запятую):</label>
            <input type="text" name="responsibilities" placeholder="Разработка, Тестирование">
        </div>
        <div class="form-group">
            <label>Необходимые навыки (через запятую):</label>
            <input type="text" name="skills_required" placeholder="Python, JavaScript, SQL">
        </div>
        <div class="form-group">
            <label>Требуемый опыт (лет):</label>
            <input type="number" name="experience_required" required>
        </div>
        <button type="submit">Добавить вакансию</button>
    </form>
    """

    jobs_list = "".join([
        f"""
        <div class="job-item">
            <h3>{job.get('title', 'N/A')}</h3>
            <p><strong>Требуемый опыт:</strong> {job.get('experience_required', 0)} лет</p>
            <p><strong>Требования:</strong> {', '.join(job.get('requirements', []))}</p>
            <p><strong>Обязанности:</strong> {', '.join(job.get('responsibilities', []))}</p>
            <p><strong>Навыки:</strong> {', '.join(job.get('skills_required', []))}</p>
            <p><strong>Создано:</strong> {job.get('created_at', 'N/A')}</p>
        </div>
        """ for job in jobs
    ])

    content = f"""
    <h1>Управление вакансиями</h1>
    {form_html}
    <h2>Список вакансий ({len(jobs)})</h2>
    {jobs_list}
    """

    html = base_html_template("Управление вакансиями", content, user)
    return web.Response(text=html, content_type='text/html')


async def analyses_page(request: Request) -> Response:
    """Страница просмотра анализов"""
    user = await get_current_user(request)
    analyses_result = await analysis_storage.read_all()
    resumes_result = await resume_storage.read_all()
    jobs_result = await job_storage.read_all()

    analyses = analyses_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )
    resumes = resumes_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )
    jobs = jobs_result.fold(
        success_func=lambda data: data,
        error_func=lambda e: []
    )

    # Создаем словари для быстрого поиска
    resume_dict = {r['id']: r for r in resumes}
    job_dict = {j['id']: j for j in jobs}

    analyses_list = "".join([
        f"""
        <div class="analysis-item">
            <h3>Анализ для {resume_dict.get(analysis.get('resume_id', {}), {}).get('name', 'N/A')}</h3>
            <p><strong>Релевантность:</strong> {analysis.get('job_match_percentage', 0)}%</p>
            <p><strong>Оценка:</strong> {analysis.get('relevance_score', 0)}/1.0</p>
            <p><strong>Анализ:</strong> {analysis.get('analysis_text', 'N/A')}</p>
            <p><strong>Дата:</strong> {analysis.get('created_at', 'N/A')}</p>
        </div>
        """ for analysis in analyses
    ])

    content = f"""
    <h1>Анализы релевантности</h1>
    <h2>Результаты анализа ({len(analyses)})</h2>
    {analyses_list}
    """

    html = base_html_template("Анализы релевантности", content, user)
    return web.Response(text=html, content_type='text/html')


# Добавьте остальные API обработчики
@with_error_handling
@with_json_response
async def create_job(request: Request) -> Dict[str, Any]:
    """API: Создание вакансии"""
    data = await request.json()
    result = await job_storage.add_item(data)

    return result.fold(
        success_func=lambda job_id: {"id": job_id, "message": "Вакансия создана успешно"},
        error_func=lambda e: {"error": str(e)}
    )


# Функциональная композиция маршрутов
def create_routes(app: web.Application) -> None:
    """Создание маршрутов с функциональным подходом"""

    # Статические маршруты
    routes = [
        ('GET', '/', index),
        ('GET', '/resumes', resumes_page),
        ('GET', '/jobs', jobs_page),
        ('GET', '/analyses', analyses_page),
    ]

    # API маршруты
    api_routes = [
        ('POST', '/api/resumes', create_resume),
        ('GET', '/api/resumes', get_resumes),
        ('POST', '/api/jobs', create_job),
        ('GET', '/api/jobs', get_jobs),
        ('POST', '/api/analyze', analyze_resume),
        ('GET', '/api/analyses', get_analyses),
        ('POST', '/api/import/hh', import_hh_resume),
    ]

    # Auth маршруты
    auth_routes = [
        ('GET', '/login', login_page),
        ('POST', '/login', login_post),
        ('GET', '/register', register_page),
        ('POST', '/register', register_post),
        ('GET', '/logout', logout),
        ('GET', '/admin', admin_page),
    ]

    # Добавление всех маршрутов
    for method, path, handler in routes + api_routes + auth_routes:
        app.router.add_route(method, path, handler)


# Каррирование для создания специализированных обработчиков
def create_json_handler(handler_func: Callable) -> Callable:
    """Фабрика для создания JSON обработчиков"""
    return compose(
        with_error_handling,
        with_json_response
    )(handler_func)


def create_protected_handler(handler_func: Callable, *predicates: Callable) -> Callable:
    """Фабрика для создания защищенных обработчиков"""
    protected = require_login(handler_func)
    for predicate in predicates:
        protected = predicate(protected)
    return protected


def create_app() -> web.Application:
    """Создание приложения aiohttp с функциональным подходом"""
    app = web.Application(middlewares=[logging_middleware_fp])

    create_routes(app)

    app.router.add_get('/create-admin', create_admin_page)
    app.router.add_post('/create-admin', create_admin_post)

    app.router.add_get('/api/debug/analysis', debug_analysis)

    return app


if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host=HOST, port=PORT)
import json
from typing import List, Dict, Any, Optional, Callable, Tuple, TypeVar
from dataclasses import dataclass
from functools import wraps, reduce, partial
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


T = TypeVar('T')
StorageData = List[Dict[str, Any]]
Predicate = Callable[[Dict[str, Any]], bool]
UpdateFunction = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class StorageOperation:
    """Иммутабельная операция хранилища"""
    action: str
    data: Optional[Any] = None
    filters: Optional[Dict[str, Any]] = None
    item_id: Optional[str] = None
    updates: Optional[Dict[str, Any]] = None


@dataclass
class StorageResult:
    """Монадический результат операции хранилища"""
    data: Optional[Any] = None
    success: bool = True
    error: Optional[Exception] = None
    operation: Optional[StorageOperation] = None

    def is_success(self) -> bool:
        return self.success and self.error is None

    def map(self, func: Callable[[Any], T]) -> 'StorageResult':
        """Functor map для преобразования данных"""
        if self.success and self.data is not None:
            try:
                return StorageResult(data=func(self.data), operation=self.operation)
            except Exception as e:
                return StorageResult(success=False, error=e, operation=self.operation)
        return self

    def bind(self, func: Callable[[Any], 'StorageResult']) -> 'StorageResult':
        """Monadic bind для цепочек операций"""
        if self.success and self.data is not None:
            return func(self.data)
        return self

    def fold(self, success_func: Callable[[Any], T], error_func: Callable[[Exception], T]) -> T:
        """Catamorphism для извлечения результата"""
        if self.success and self.data is not None:
            return success_func(self.data)
        return error_func(self.error) if self.error else error_func(Exception("Unknown error"))



def generate_item_id() -> str:
    """Чистая функция генерации ID"""
    return str(uuid.uuid4())


def get_current_timestamp() -> datetime:
    """Чистая функция получения времени"""
    return datetime.now()


def enrich_item_with_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    """Чистая функция добавления метаданных к элементу"""
    return {
        **item,
        'id': item.get('id') or generate_item_id(),
        'created_at': item.get('created_at') or get_current_timestamp(),
        'updated_at': get_current_timestamp()
    }


def update_item_timestamp(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Чистая функция обновления временных меток"""
    return {
        **updates,
        'updated_at': get_current_timestamp()
    }


def create_predicate_from_filters(filters: Dict[str, Any]) -> Predicate:
    """Фабрика предикатов из фильтров"""

    def predicate(item: Dict[str, Any]) -> bool:
        return all(item.get(key) == value for key, value in filters.items())

    return predicate



def with_storage_fallback(default_value: Any) -> Callable:
    """Декоратор для добавления fallback значений"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Storage operation failed: {e}")
                return default_value

        return wrapper

    return decorator


def retry_on_failure(max_attempts: int = 3) -> Callable:
    """Декоратор для повторных попыток"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
                    if attempt == max_attempts - 1:
                        break
            raise last_exception or Exception("All storage attempts failed")

        return wrapper

    return decorator



def compose_operations(*operations: Callable) -> Callable:
    """Композиция операций хранилища"""
    return reduce(lambda f, g: lambda x: g(f(x)), operations)



class Maybe:
    """Maybe монада для безопасной обработки значений"""

    def __init__(self, value: Optional[T]):
        self.value = value

    def map(self, func: Callable[[T], U]) -> 'Maybe':
        """Применяет функцию к значению если оно существует"""
        if self.value is not None:
            try:
                return Maybe(func(self.value))
            except Exception:
                return Maybe(None)
        return self

    def bind(self, func: Callable[[T], 'Maybe']) -> 'Maybe':
        """Цепочка операций"""
        if self.value is not None:
            return func(self.value)
        return self

    def filter(self, predicate: Callable[[T], bool]) -> 'Maybe':
        """Фильтрация значения"""
        if self.value is not None and predicate(self.value):
            return self
        return Maybe(None)

    def or_else(self, default: T) -> T:
        """Возвращает значение или значение по умолчанию"""
        return self.value if self.value is not None else default



class MemoryStorage:
    def __init__(self, name: str = None):
        """
        Инициализация хранилища в оперативной памяти
        
        Args:
            name: Имя хранилища (для обратной совместимости, игнорируется)
        """
        self._data: StorageData = []
        self._name = name

    async def _read_data(self) -> StorageData:
        """Читает все данные из памяти"""
        return self._data.copy()

    async def _write_data(self, data: StorageData) -> None:
        """Записывает все данные в память"""
        self._data = data.copy()

    async def write_all(self, data: StorageData) -> StorageResult:
        """Записывает все данные (для обратной совместимости)"""
        try:
            await self._write_data(data)
            return StorageResult(data=True)
        except Exception as e:
            logger.error(f"Write all failed: {e}")
            return StorageResult(success=False, error=e)

    async def load(self) -> Dict[str, Any]:
        """Загружает данные в виде словаря (для обратной совместимости)"""
        try:
            data = await self._read_data()
            return {item.get('id', str(i)): item for i, item in enumerate(data)}
        except Exception as e:
            logger.error(f"Load failed: {e}")
            return {}

    async def execute_operation(self, operation: StorageOperation) -> StorageResult:
        """Выполняет операцию над хранилищем"""
        try:
            if operation.action == 'read_all':
                data = await self._read_data()
                return StorageResult(data=data, operation=operation)

            elif operation.action == 'add_item':
                enriched_item = enrich_item_with_metadata(operation.data)
                data = await self._read_data()
                new_data = data + [enriched_item]
                await self._write_data(new_data)
                return StorageResult(data=enriched_item['id'], operation=operation)

            elif operation.action == 'get_item':
                data = await self._read_data()
                item = Maybe(data).bind(
                    lambda d: Maybe(next((item for item in d if item.get('id') == operation.item_id), None))
                ).or_else(None)
                return StorageResult(data=item, operation=operation)

            elif operation.action == 'update_item':
                data = await self._read_data()

                def update_single_item(item: Dict[str, Any]) -> Dict[str, Any]:
                    if item.get('id') == operation.item_id:
                        return {**item, **update_item_timestamp(operation.updates or {})}
                    return item

                updated_data = [update_single_item(item) for item in data]
                was_updated = any(item.get('id') == operation.item_id for item in data)

                if was_updated:
                    await self._write_data(updated_data)
                    return StorageResult(data=True, operation=operation)
                else:
                    return StorageResult(data=False, operation=operation)

            elif operation.action == 'delete_item':
                data = await self._read_data()
                filtered_data = [item for item in data if item.get('id') != operation.item_id]
                was_deleted = len(data) != len(filtered_data)

                if was_deleted:
                    await self._write_data(filtered_data)
                    return StorageResult(data=True, operation=operation)
                else:
                    return StorageResult(data=False, operation=operation)

            elif operation.action == 'find_items':
                data = await self._read_data()
                predicate = create_predicate_from_filters(operation.filters or {})
                results = list(filter(predicate, data))
                return StorageResult(data=results, operation=operation)

            else:
                raise ValueError(f"Unknown operation: {operation.action}")

        except Exception as e:
            logger.error(f"Operation {operation.action} failed: {e}")
            return StorageResult(success=False, error=e, operation=operation)


    async def read_all(self) -> StorageResult:
        """Читает все данные из файла"""
        operation = StorageOperation(action='read_all')
        return await self.execute_operation(operation)

    async def add_item(self, item: Dict[str, Any]) -> StorageResult:
        """Добавляет новый элемент и возвращает его ID"""
        operation = StorageOperation(action='add_item', data=item)
        return await self.execute_operation(operation)

    async def get_item(self, item_id: str) -> StorageResult:
        """Получает элемент по ID"""
        operation = StorageOperation(action='get_item', item_id=item_id)
        return await self.execute_operation(operation)

    async def update_item(self, item_id: str, updates: Dict[str, Any]) -> StorageResult:
        """Обновляет элемент по ID"""
        operation = StorageOperation(action='update_item', item_id=item_id, updates=updates)
        return await self.execute_operation(operation)

    async def delete_item(self, item_id: str) -> StorageResult:
        """Удаляет элемент по ID"""
        operation = StorageOperation(action='delete_item', item_id=item_id)
        return await self.execute_operation(operation)

    async def find_items(self, filters: Dict[str, Any]) -> StorageResult:
        """Находит элементы по фильтрам"""
        operation = StorageOperation(action='find_items', filters=filters)
        return await self.execute_operation(operation)

    # Функциональные методы для работы с данными
    async def find_first(self, predicate: Predicate) -> StorageResult:
        """Находит первый элемент, удовлетворяющий предикату"""
        return await self.read_all().bind(
            lambda data: StorageResult(
                data=Maybe(data).bind(
                    lambda d: Maybe(next((item for item in d if predicate(item)), None))
                ).or_else(None)
            )
        )

    async def update_where(self, predicate: Predicate, update_func: UpdateFunction) -> StorageResult:
        """Обновляет все элементы, удовлетворяющие предикату"""
        return await self.read_all().bind(
            lambda data: self._update_multiple_items(data, predicate, update_func)
        )

    async def _update_multiple_items(self, data: StorageData, predicate: Predicate,
                                     update_func: UpdateFunction) -> StorageResult:
        """Обновляет несколько элементов"""
        updated_data = []
        updated_count = 0

        for item in data:
            if predicate(item):
                updated_item = update_func(update_item_timestamp(item))
                updated_data.append(updated_item)
                updated_count += 1
            else:
                updated_data.append(item)

        if updated_count > 0:
            await self._write_data(updated_data)
            return StorageResult(data=updated_count)
        else:
            return StorageResult(data=0)

    async def transactional_operation(self, *operations: StorageOperation) -> StorageResult:
        """Выполняет несколько операций в транзакции"""
        original_data = await self._read_data()

        try:
            results = []
            current_data = original_data.copy()

            for operation in operations:
                result = await self.execute_operation(operation)
                results.append(result)

                if not result.is_success():
                    await self._write_data(original_data)
                    return StorageResult(
                        success=False,
                        error=Exception("Transaction failed"),
                        data=results
                    )

            return StorageResult(data=results)

        except Exception as e:
            # Откат при любой ошибке
            await self._write_data(original_data)
            return StorageResult(success=False, error=e)



def create_storage_pipeline(*operations: Callable) -> Callable:
    """Создает pipeline операций хранилища"""

    async def async_compose(f, g):
        return lambda x: g(f(x))

    return reduce(async_compose, operations)


def with_transaction(storage: MemoryStorage) -> Callable:
    """Декоратор для выполнения операций в транзакции"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            original_data = await storage._read_data()

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                await storage._write_data(original_data)
                logger.error(f"Transaction failed, rolled back: {e}")
                raise

        return wrapper

    return decorator



def has_key_value(key: str, value: Any) -> Predicate:
    """Создает предикат для проверки ключ-значение"""
    return lambda item: item.get(key) == value


def has_key_in_list(key: str, values: List[Any]) -> Predicate:
    """Создает предикат для проверки наличия значения в списке"""
    return lambda item: item.get(key) in values


def created_after(timestamp: datetime) -> Predicate:
    """Создает предикат для фильтрации по дате создания"""
    return lambda item: item.get('created_at', datetime.min) > timestamp



JSONStorageFP = MemoryStorage
JSONStorage = MemoryStorage


async def example_usage():
    storage = MemoryStorage("users")


    pipeline = create_storage_pipeline(
        lambda user: storage.add_item(user),
        lambda result: result.map(lambda id: f"Created user with ID: {id}")
    )

    user_data = {"name": "John", "email": "john@example.com"}
    result = await pipeline(user_data)


    message = result.fold(
        success_func=lambda msg: msg,
        error_func=lambda e: f"Error: {e}"
    )

    print(message)


    find_result = await storage.find_first(has_key_value("name", "John"))

    user = find_result.fold(
        success_func=lambda u: u,
        error_func=lambda e: None
    )


    @with_transaction(storage)
    async def transfer_data():
        await storage.delete_item("old_id")
        await storage.add_item({"name": "New User"})

    await transfer_data()
import json
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict


class DateTimeEncoder(json.JSONEncoder):
    """Кастомный JSON encoder для обработки datetime и других несериализуемых типов"""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        elif hasattr(obj, 'dict') and callable(getattr(obj, 'dict')):
            # Для Pydantic моделей
            return obj.dict()
        elif hasattr(obj, '__dict__'):
            # Для обычных объектов
            return obj.__dict__
        return super().default(obj)


def json_serialize(data: Any) -> str:
    """Сериализует данные в JSON с обработкой datetime"""
    return json.dumps(data, cls=DateTimeEncoder, ensure_ascii=False, indent=2)


def safe_json_response(data: Any, status: int = 200) -> Any:
    """Создает безопасный JSON response"""
    from aiohttp import web
    return web.Response(
        text=json_serialize(data),
        content_type='application/json',
        status=status
    )
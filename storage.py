import json
import aiofiles
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

class JSONStorage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Создает файл если он не существует"""
        if not os.path.exists(self.file_path):
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
    
    async def read_all(self) -> List[Dict[str, Any]]:
        """Читает все данные из файла"""
        try:
            async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content) if content.strip() else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    async def write_all(self, data: List[Dict[str, Any]]) -> None:
        """Записывает все данные в файл"""
        async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    
    async def add_item(self, item: Dict[str, Any]) -> str:
        """Добавляет новый элемент и возвращает его ID"""
        data = await self.read_all()
        item_id = str(uuid.uuid4())
        item['id'] = item_id
        item['created_at'] = datetime.now()
        item['updated_at'] = datetime.now()
        data.append(item)
        await self.write_all(data)
        return item_id
    
    async def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Получает элемент по ID"""
        data = await self.read_all()
        for item in data:
            if item.get('id') == item_id:
                return item
        return None
    
    async def update_item(self, item_id: str, updates: Dict[str, Any]) -> bool:
        """Обновляет элемент по ID"""
        data = await self.read_all()
        for i, item in enumerate(data):
            if item.get('id') == item_id:
                data[i].update(updates)
                data[i]['updated_at'] = datetime.now()
                await self.write_all(data)
                return True
        return False
    
    async def delete_item(self, item_id: str) -> bool:
        """Удаляет элемент по ID"""
        data = await self.read_all()
        for i, item in enumerate(data):
            if item.get('id') == item_id:
                del data[i]
                await self.write_all(data)
                return True
        return False
    
    async def find_items(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Находит элементы по фильтрам"""
        data = await self.read_all()
        results = []
        for item in data:
            match = True
            for key, value in filters.items():
                if item.get(key) != value:
                    match = False
                    break
            if match:
                results.append(item)
        return results





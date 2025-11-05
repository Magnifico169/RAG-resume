#!/usr/bin/env python3
"""
Демонстрационный скрипт для тестирования API системы анализа резюме
"""

import asyncio
import aiohttp
import json

BASE_URL = "http://localhost:8080"

async def test_api():
    """Тестирование API функций"""
    async with aiohttp.ClientSession() as session:
        
        print("🚀 Тестирование API системы анализа резюме\n")
        
        # 1. Создание резюме
        print("1. Создание резюме...")
        resume_data = {
            "name": "Алексей Иванов",
            "position": "Python Developer",
            "experience": 4,
            "skills": ["Python", "Django", "PostgreSQL", "Docker", "Git"],
            "education": "Высшее техническое образование",
            "languages": ["Русский", "Английский"],
            "contact_info": {
                "email": "alexey@example.com",
                "phone": "+7-999-123-45-67"
            }
        }
        
        async with session.post(f"{BASE_URL}/api/resumes", json=resume_data) as resp:
            if resp.status == 200:
                result = await resp.json()
                resume_id = result["id"]
                print(f"✅ Резюме создано с ID: {resume_id}")
            else:
                print(f"❌ Ошибка создания резюме: {resp.status}")
                return
        
        # 2. Создание вакансии
        print("\n2. Создание вакансии...")
        job_data = {
            "title": "Senior Python Developer",
            "requirements": ["Опыт работы 3+ лет", "Высшее техническое образование"],
            "responsibilities": ["Разработка backend приложений", "Code review", "Менторство"],
            "skills_required": ["Python", "Django", "PostgreSQL", "Docker", "Redis"],
            "experience_required": 3
        }
        
        async with session.post(f"{BASE_URL}/api/jobs", json=job_data) as resp:
            if resp.status == 200:
                result = await resp.json()
                job_id = result["id"]
                print(f"✅ Вакансия создана с ID: {job_id}")
            else:
                print(f"❌ Ошибка создания вакансии: {resp.status}")
                return
        
        # 3. Анализ релевантности
        print("\n3. Анализ релевантности резюме...")
        analysis_data = {
            "resume_id": resume_id,
            "job_id": job_id
        }
        
        async with session.post(f"{BASE_URL}/api/analyze", json=analysis_data) as resp:
            if resp.status == 200:
                analysis_result = await resp.json()
                print("✅ Анализ завершен!")
                print(f"   Релевантность: {analysis_result['job_match_percentage']}%")
                print(f"   Оценка: {analysis_result['relevance_score']}/1.0")
                print(f"   Сильные стороны: {', '.join(analysis_result['strengths'])}")
                print(f"   Слабые стороны: {', '.join(analysis_result['weaknesses'])}")
                print(f"   Рекомендации: {', '.join(analysis_result['recommendations'])}")
            else:
                print(f"❌ Ошибка анализа: {resp.status}")
                error_text = await resp.text()
                print(f"   Детали: {error_text}")
        
        # 4. Получение всех резюме
        print("\n4. Получение списка резюме...")
        async with session.get(f"{BASE_URL}/api/resumes") as resp:
            if resp.status == 200:
                resumes = await resp.json()
                print(f"✅ Найдено резюме: {len(resumes)}")
                for resume in resumes:
                    print(f"   - {resume['name']} ({resume['position']})")
            else:
                print(f"❌ Ошибка получения резюме: {resp.status}")
        
        # 5. Получение всех вакансий
        print("\n5. Получение списка вакансий...")
        async with session.get(f"{BASE_URL}/api/jobs") as resp:
            if resp.status == 200:
                jobs = await resp.json()
                print(f"✅ Найдено вакансий: {len(jobs)}")
                for job in jobs:
                    print(f"   - {job['title']}")
            else:
                print(f"❌ Ошибка получения вакансий: {resp.status}")
        
        # 6. Получение всех анализов
        print("\n6. Получение списка анализов...")
        async with session.get(f"{BASE_URL}/api/analyses") as resp:
            if resp.status == 200:
                analyses = await resp.json()
                print(f"✅ Найдено анализов: {len(analyses)}")
                for analysis in analyses:
                    print(f"   - Анализ для резюме {analysis['resume_id']}: {analysis['job_match_percentage']}%")
            else:
                print(f"❌ Ошибка получения анализов: {resp.status}")
        
        print("\n🎉 Тестирование завершено!")
        print(f"🌐 Веб-интерфейс доступен по адресу: {BASE_URL}")

if __name__ == "__main__":
    print("Убедитесь, что сервер запущен (python main.py)")
    print("Нажмите Enter для продолжения...")
    input()
    asyncio.run(test_api())





#!/usr/bin/env python3
"""
Диагностический скрипт для проверки системы анализа
"""

import asyncio
import aiohttp
import json
import sys

BASE_URL = "http://localhost:8080"


async def run_diagnostics():
    """Запуск диагностики системы"""
    print("🔧 Running system diagnostics...")

    async with aiohttp.ClientSession() as session:

        print("1. Checking server availability...")
        try:
            async with session.get(f"{BASE_URL}/") as resp:
                if resp.status == 200:
                    print("   ✅ Server is running")
                else:
                    print(f"   ❌ Server returned status: {resp.status}")
                    return False
        except Exception as e:
            print(f"   ❌ Cannot connect to server: {e}")
            return False

        print("2. Checking analysis debug endpoint...")
        try:
            async with session.get(f"{BASE_URL}/api/debug/analysis") as resp:
                data = await resp.json()
                print(f"   ✅ Debug endpoint response: {json.dumps(data, indent=2, ensure_ascii=False)}")
        except Exception as e:
            print(f"   ❌ Debug endpoint failed: {e}")

        # 3. Проверка создания резюме
        print("3. Testing resume creation...")
        resume_data = {
            "name": "Диагностический Кандидат",
            "position": "Test Developer",
            "experience": 2,
            "skills": ["Python", "Testing"],
            "education": "Test Education",
            "languages": ["Русский"],
            "contact_info": {
                "email": "test@example.com",
                "phone": "+7-000-000-00-00"
            }
        }

        try:
            async with session.post(f"{BASE_URL}/api/resumes", json=resume_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"   ✅ Resume created: {result['id']}")
                    resume_id = result['id']
                else:
                    print(f"   ❌ Resume creation failed: {resp.status}")
                    return False
        except Exception as e:
            print(f"   ❌ Resume creation error: {e}")
            return False

        print("4. Testing job creation...")
        job_data = {
            "title": "Test Developer",
            "requirements": ["Опыт работы 1+ год"],
            "responsibilities": ["Тестирование системы"],
            "skills_required": ["Python", "Testing"],
            "experience_required": 1
        }

        try:
            async with session.post(f"{BASE_URL}/api/jobs", json=job_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"   ✅ Job created: {result['id']}")
                    job_id = result['id']
                else:
                    print(f"   ❌ Job creation failed: {resp.status}")
                    return False
        except Exception as e:
            print(f"   ❌ Job creation error: {e}")
            return False

        print("5. Testing analysis...")
        analysis_data = {
            "resume_id": resume_id,
            "job_id": job_id
        }

        try:
            async with session.post(f"{BASE_URL}/api/analyze", json=analysis_data) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print("   ✅ Analysis completed successfully!")
                    print(f"   📊 Results: {json.dumps(result, indent=2, ensure_ascii=False)}")
                    return True
                else:
                    error_text = await resp.text()
                    print(f"   ❌ Analysis failed: {resp.status}")
                    print(f"   Error details: {error_text}")
                    return False
        except Exception as e:
            print(f"   ❌ Analysis error: {e}")
            return False


if __name__ == "__main__":
    print("🚀 Starting comprehensive diagnostics...")
    success = asyncio.run(run_diagnostics())

    if success:
        print("\n🎉 All diagnostics passed! System is working correctly.")
    else:
        print("\n💥 Some diagnostics failed. Check the logs above.")
        sys.exit(1)
import aiohttp
from aiohttp import web, web_request
from aiohttp.web import Request, Response
import json
from typing import Dict, Any
from datetime import datetime
import uuid

from models import Resume, AnalysisResult, JobDescription
from storage import JSONStorage
from rag_analyzer import RAGAnalyzer
from config import DATA_DIR, RESUMES_FILE, ANALYSES_FILE, HOST, PORT
from auth import users_storage, hash_password, verify_password, get_current_user, require_login, require_admin

# Инициализация хранилищ
resume_storage = JSONStorage(f"{DATA_DIR}/{RESUMES_FILE}")
analysis_storage = JSONStorage(f"{DATA_DIR}/{ANALYSES_FILE}")
job_storage = JSONStorage(f"{DATA_DIR}/jobs.json")
logs_storage = JSONStorage(f"{DATA_DIR}/logs.json")

# Инициализация RAG анализатора
rag_analyzer = RAGAnalyzer()

async def index(request: Request) -> Response:
    """Главная страница"""
    user = await get_current_user(request)
    username = user['username'] if user else 'Гость'
    auth_link = '<a href="/logout">Выйти</a>' if user else '<a href="/login">Войти</a>'
    return web.Response(text=f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Система анализа резюме</title>
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
            <div class="nav">
                <a href="/">Главная</a>
                <a href="/resumes">Резюме</a>
                <a href="/jobs">Вакансии</a>
                <a href="/analyses">Анализы</a>
                <a href="/admin">Админ</a>
                <span class="badge">{username}</span>
                {auth_link}
            </div>
            <div class="hero">
                <h1>Система анализа релевантности резюме</h1>
                <p>Анализируйте соответствие кандидатов вакансиям с помощью RAG. Хранение — только JSON.</p>
                <div class="grid">
                    <div class="card"><h3>Резюме</h3><p>Создавайте и импортируйте резюме из hh.ru.</p></div>
                    <div class="card"><h3>Вакансии</h3><p>Добавляйте описания и требования.</p></div>
                    <div class="card"><h3>Анализ</h3><p>Автоматический разбор релевантности.</p></div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """, content_type='text/html')

async def resumes_page(request: Request) -> Response:
    """Страница управления резюме"""
    resumes = await resume_storage.read_all()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Управление резюме</title>
        <meta charset="utf-8">
        <style>
            :root {{ --bg:#f5f5f7; --card:#ffffff; --text:#1d1d1f; --muted:#6e6e73; --accent:#0071e3; --radius:18px; --shadow:0 8px 30px rgba(0,0,0,0.06); }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif; margin: 0; background: var(--bg); color: var(--text); }}
            .container {{ max-width: 1000px; margin: 0 auto; padding: 40px 24px; }}
            .nav {{ margin: 0 0 24px; }}
            .nav a {{ margin-right: 12px; text-decoration: none; color: var(--text); padding: 8px 12px; border-radius: 12px; }}
            .nav a:hover {{ background: #e8e8ed; }}
            .form-group {{ margin: 12px 0; }}
            label {{ display: block; margin-bottom: 6px; font-weight: 600; }}
            input, textarea, select {{ width: 100%; padding: 10px 12px; border: 1px solid #e5e5ea; border-radius: 12px; background: #fff; }}
            button {{ background: var(--accent); color: white; padding: 10px 16px; border: none; border-radius: 999px; cursor: pointer; }}
            button:hover {{ filter: brightness(0.95); }}
            .resume-item {{ background: var(--card); border: 1px solid #eee; padding: 16px; margin: 10px 0; border-radius: var(--radius); box-shadow: var(--shadow); }}
            .skills {{ color: var(--muted); }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Управление резюме</h1>
            <div class="nav">
                <a href="/">Главная</a>
                <a href="/resumes">Резюме</a>
                <a href="/jobs">Вакансии</a>
                <a href="/analyses">Анализы</a>
            </div>
            
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
                <textarea id="hhJson" rows="10" placeholder="{{'first_name': 'Иван', ...}}"></textarea>
            </div>
            <button id="importHh">Импортировать из hh.ru</button>
            
            <h2>Список резюме ({len(resumes)})</h2>
    """
    
    for resume in resumes:
        skills_str = ', '.join(resume.get('skills', []))
        html += f"""
            <div class="resume-item">
                <h3>{resume.get('name', 'N/A')} - {resume.get('position', 'N/A')}</h3>
                <p><strong>Опыт:</strong> {resume.get('experience', 0)} лет</p>
                <p><strong>Навыки:</strong> <span class="skills">{skills_str}</span></p>
                <p><strong>Образование:</strong> {resume.get('education', 'N/A')}</p>
                <p><strong>Языки:</strong> {', '.join(resume.get('languages', []))}</p>
                <p><strong>Контакты:</strong> {resume.get('contact_info', {}).get('email', 'N/A')}, {resume.get('contact_info', {}).get('phone', 'N/A')}</p>
                <p><strong>Создано:</strong> {resume.get('created_at', 'N/A')}</p>
            </div>
        """
    
    html += """
        </div>
        <script>
            document.getElementById('resumeForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                const formData = new FormData(e.target);
                const data = {
                    name: formData.get('name'),
                    position: formData.get('position'),
                    experience: parseInt(formData.get('experience')),
                    skills: formData.get('skills').split(',').map(s => s.trim()).filter(s => s),
                    education: formData.get('education'),
                    languages: formData.get('languages').split(',').map(s => s.trim()).filter(s => s),
                    contact_info: {
                        email: formData.get('email'),
                        phone: formData.get('phone')
                    }
                };
                
                const response = await fetch('/api/resumes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                if (response.ok) {
                    location.reload();
                } else {
                    alert('Ошибка при добавлении резюме');
                }
            });

            document.getElementById('importHh').addEventListener('click', async function() {
                const raw = document.getElementById('hhJson').value;
                if (!raw.trim()) { alert('Вставьте JSON из hh.ru'); return; }
                try {
                    const parsed = JSON.parse(raw);
                    const response = await fetch('/api/import/hh', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(parsed)
                    });
                    if (response.ok) {
                        location.reload();
                    } else {
                        const txt = await response.text();
                        alert('Ошибка импорта: ' + txt);
                    }
                } catch (err) {
                    alert('Некорректный JSON: ' + err);
                }
            });
        </script>
    </body>
    </html>
    """
    
    return web.Response(text=html, content_type='text/html')

async def jobs_page(request: Request) -> Response:
    """Страница управления вакансиями"""
    jobs = await job_storage.read_all()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Управление вакансиями</title>
        <meta charset="utf-8">
        <style>
            :root {{ --bg:#f5f5f7; --card:#ffffff; --text:#1d1d1f; --muted:#6e6e73; --accent:#0071e3; --radius:18px; --shadow:0 8px 30px rgba(0,0,0,0.06); }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif; margin: 0; background: var(--bg); color: var(--text); }}
            .container {{ max-width: 1000px; margin: 0 auto; padding: 40px 24px; }}
            .nav {{ margin: 0 0 24px; }}
            .nav a {{ margin-right: 12px; text-decoration: none; color: var(--text); padding: 8px 12px; border-radius: 12px; }}
            .nav a:hover {{ background: #e8e8ed; }}
            .form-group {{ margin: 12px 0; }}
            label {{ display: block; margin-bottom: 6px; font-weight: 600; }}
            input, textarea, select {{ width: 100%; padding: 10px 12px; border: 1px solid #e5e5ea; border-radius: 12px; background: #fff; }}
            button {{ background: var(--accent); color: white; padding: 10px 16px; border: none; border-radius: 999px; cursor: pointer; }}
            button:hover {{ filter: brightness(0.95); }}
            .job-item {{ background: var(--card); border: 1px solid #eee; padding: 16px; margin: 10px 0; border-radius: var(--radius); box-shadow: var(--shadow); }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Управление вакансиями</h1>
            <div class="nav">
                <a href="/">Главная</a>
                <a href="/resumes">Резюме</a>
                <a href="/jobs">Вакансии</a>
                <a href="/analyses">Анализы</a>
            </div>
            
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
            
            <h2>Список вакансий ({len(jobs)})</h2>
    """
    
    for job in jobs:
        html += f"""
            <div class="job-item">
                <h3>{job.get('title', 'N/A')}</h3>
                <p><strong>Требуемый опыт:</strong> {job.get('experience_required', 0)} лет</p>
                <p><strong>Требования:</strong> {', '.join(job.get('requirements', []))}</p>
                <p><strong>Обязанности:</strong> {', '.join(job.get('responsibilities', []))}</p>
                <p><strong>Навыки:</strong> {', '.join(job.get('skills_required', []))}</p>
                <p><strong>Создано:</strong> {job.get('created_at', 'N/A')}</p>
            </div>
        """
    
    html += """
        </div>
        <script>
            document.getElementById('jobForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                const formData = new FormData(e.target);
                const data = {
                    title: formData.get('title'),
                    requirements: formData.get('requirements').split(',').map(s => s.trim()).filter(s => s),
                    responsibilities: formData.get('responsibilities').split(',').map(s => s.trim()).filter(s => s),
                    skills_required: formData.get('skills_required').split(',').map(s => s.trim()).filter(s => s),
                    experience_required: parseInt(formData.get('experience_required'))
                };
                
                const response = await fetch('/api/jobs', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                if (response.ok) {
                    location.reload();
                } else {
                    alert('Ошибка при добавлении вакансии');
                }
            });
        </script>
    </body>
    </html>
    """
    
    return web.Response(text=html, content_type='text/html')

async def analyses_page(request: Request) -> Response:
    """Страница просмотра анализов"""
    analyses = await analysis_storage.read_all()
    resumes = await resume_storage.read_all()
    jobs = await job_storage.read_all()
    
    # Создаем словари для быстрого поиска
    resume_dict = {r['id']: r for r in resumes}
    job_dict = {j['id']: j for j in jobs}
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Анализы релевантности</title>
        <meta charset="utf-8">
        <style>
            :root {{ --bg:#f5f5f7; --card:#ffffff; --text:#1d1d1f; --muted:#6e6e73; --accent:#0071e3; --radius:18px; --shadow:0 8px 30px rgba(0,0,0,0.06); }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif; margin: 0; background: var(--bg); color: var(--text); }}
            .container {{ max-width: 1000px; margin: 0 auto; padding: 40px 24px; }}
            .nav {{ margin: 0 0 24px; }}
            .nav a {{ margin-right: 12px; text-decoration: none; color: var(--text); padding: 8px 12px; border-radius: 12px; }}
            .nav a:hover {{ background: #e8e8ed; }}
            .analysis-item {{ background: var(--card); border: 1px solid #eee; padding: 16px; margin: 10px 0; border-radius: var(--radius); box-shadow: var(--shadow); }}
            .score {{ font-size: 18px; font-weight: bold; color: #28a745; }}
            .strengths {{ color: #28a745; }}
            .weaknesses {{ color: #dc3545; }}
            .recommendations {{ color: #007bff; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Анализы релевантности</h1>
            <div class="nav">
                <a href="/">Главная</a>
                <a href="/resumes">Резюме</a>
                <a href="/jobs">Вакансии</a>
                <a href="/analyses">Анализы</a>
            </div>
            
            <h2>Результаты анализа ({len(analyses)})</h2>
    """
    
    for analysis in analyses:
        resume = resume_dict.get(analysis.get('resume_id', ''), {})
        html += f"""
            <div class="analysis-item">
                <h3>Анализ для {resume.get('name', 'N/A')}</h3>
                <p><strong>Позиция:</strong> {resume.get('position', 'N/A')}</p>
                <p><strong>Релевантность:</strong> <span class="score">{analysis.get('job_match_percentage', 0)}%</span></p>
                <p><strong>Оценка:</strong> {analysis.get('relevance_score', 0)}/1.0</p>
                
                <h4>Сильные стороны:</h4>
                <ul class="strengths">
        """
        for strength in analysis.get('strengths', []):
            html += f"<li>{strength}</li>"
        
        html += """
                </ul>
                
                <h4>Слабые стороны:</h4>
                <ul class="weaknesses">
        """
        for weakness in analysis.get('weaknesses', []):
            html += f"<li>{weakness}</li>"
        
        html += """
                </ul>
                
                <h4>Рекомендации:</h4>
                <ul class="recommendations">
        """
        for rec in analysis.get('recommendations', []):
            html += f"<li>{rec}</li>"
        
        html += f"""
                </ul>
                <p><strong>Подробный анализ:</strong> {analysis.get('analysis_text', 'N/A')}</p>
                <p><strong>Дата анализа:</strong> {analysis.get('created_at', 'N/A')}</p>
            </div>
        """
    
    html += """
        </div>
    </body>
    </html>
    """
    
    return web.Response(text=html, content_type='text/html')

# API маршруты
async def create_resume(request: Request) -> Response:
    """API: Создание резюме"""
    try:
        data = await request.json()
        resume_id = await resume_storage.add_item(data)
        return web.json_response({"id": resume_id, "message": "Резюме создано успешно"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

async def get_resumes(request: Request) -> Response:
    """API: Получение всех резюме"""
    resumes = await resume_storage.read_all()
    return web.json_response(resumes)

async def create_job(request: Request) -> Response:
    """API: Создание вакансии"""
    try:
        data = await request.json()
        job_id = await job_storage.add_item(data)
        return web.json_response({"id": job_id, "message": "Вакансия создана успешно"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

async def get_jobs(request: Request) -> Response:
    """API: Получение всех вакансий"""
    jobs = await job_storage.read_all()
    return web.json_response(jobs)

async def analyze_resume(request: Request) -> Response:
    """API: Анализ релевантности резюме"""
    try:
        data = await request.json()
        resume_id = data.get('resume_id')
        job_id = data.get('job_id')
        
        if not resume_id or not job_id:
            return web.json_response({"error": "Требуются resume_id и job_id"}, status=400)
        
        # Получаем данные резюме и вакансии
        resume_data = await resume_storage.get_item(resume_id)
        job_data = await job_storage.get_item(job_id)
        
        if not resume_data or not job_data:
            return web.json_response({"error": "Резюме или вакансия не найдены"}, status=404)
        
        # Создаем объекты моделей
        resume = Resume(**resume_data)
        job = JobDescription(**job_data)
        
        # Выполняем анализ
        analysis = await rag_analyzer.analyze_resume_relevance(resume, job)
        
        # Сохраняем результат анализа
        analysis_dict = analysis.dict()
        await analysis_storage.add_item(analysis_dict)
        
        return web.json_response(analysis_dict)
        
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def get_analyses(request: Request) -> Response:
    """API: Получение всех анализов"""
    analyses = await analysis_storage.read_all()
    return web.json_response(analyses)

# ------- Импорт с hh.ru -------
def map_hh_to_internal(hh: Dict[str, Any]) -> Dict[str, Any]:
    """Преобразует JSON резюме hh.ru к внутреннему формату хранения."""
    # Имя: first_name + last_name
    first_name = hh.get('first_name') or hh.get('name') or ''
    last_name = hh.get('last_name') or ''
    full_name = f"{first_name} {last_name}".strip() or hh.get('title') or 'Кандидат hh.ru'

    # Позиция: title или area/position
    position = hh.get('title') or (hh.get('position') if isinstance(hh.get('position'), str) else None) or 'Специалист'

    # Опыт (лет): из experience.total или суммируем
    experience_years = 0
    exp = hh.get('experience')
    if isinstance(exp, dict):
        total = exp.get('total')
        if isinstance(total, dict):
            # hh иногда возвращает total в месяцах: { months: 36 }
            months = total.get('months')
            if isinstance(months, int):
                experience_years = max(0, round(months / 12))
        elif isinstance(total, int):
            experience_years = max(0, round(total / 12))
        # если есть массив places, можно уточнить навыки

    # Навыки: skills -> [{name}], ключевые навыки key_skills
    skills: list[str] = []
    key_skills = hh.get('key_skills') or hh.get('skills')
    if isinstance(key_skills, list):
        for s in key_skills:
            if isinstance(s, dict) and 'name' in s and isinstance(s['name'], str):
                skills.append(s['name'])
            elif isinstance(s, str):
                skills.append(s)

    # Образование: education.level.name или first_institution
    education = 'Не указано'
    edu = hh.get('education')
    if isinstance(edu, dict):
        level = edu.get('level')
        if isinstance(level, dict) and isinstance(level.get('name'), str):
            education = level['name']

    # Языки: languages -> [{id,name,level}]
    languages: list[str] = []
    langs = hh.get('language') or hh.get('languages')
    if isinstance(langs, list):
        for l in langs:
            if isinstance(l, dict):
                name = l.get('name') or l.get('id')
                level = l.get('level')
                if isinstance(level, dict):
                    lvl_name = level.get('name')
                else:
                    lvl_name = level
                if isinstance(name, str):
                    languages.append(name if not lvl_name else f"{name} ({lvl_name})")

    # Контакты: email, phone
    contact_info = {
        'email': None,
        'phone': None,
    }
    contact = hh.get('contact') or hh.get('contacts')
    if isinstance(contact, dict):
        email = contact.get('email')
        phone = contact.get('phone')
        if isinstance(email, str):
            contact_info['email'] = email
        if isinstance(phone, dict):
            number = phone.get('formatted') or phone.get('number')
            if isinstance(number, str):
                contact_info['phone'] = number
        elif isinstance(phone, str):
            contact_info['phone'] = phone

    if not contact_info['email']:
        email = hh.get('email')
        if isinstance(email, str):
            contact_info['email'] = email

    if not contact_info['phone']:
        phones = hh.get('phones')
        if isinstance(phones, list) and phones:
            p0 = phones[0]
            if isinstance(p0, dict):
                number = p0.get('formatted') or p0.get('number')
                if isinstance(number, str):
                    contact_info['phone'] = number
            elif isinstance(p0, str):
                contact_info['phone'] = p0

    # Сборка итогового словаря
    return {
        'name': full_name,
        'position': position,
        'experience': experience_years,
        'skills': skills,
        'education': education,
        'languages': languages,
        'contact_info': {k: (v or '') for k, v in contact_info.items()},
    }

async def import_hh_resume(request: Request) -> Response:
    """API: Импорт резюме из hh.ru JSON."""
    try:
        hh_json = await request.json()
        mapped = map_hh_to_internal(hh_json)
        resume_id = await resume_storage.add_item(mapped)
        return web.json_response({"id": resume_id, "message": "Импортировано из hh.ru"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

# ------- Аутентификация и админ -------
async def login_page(request: Request) -> Response:
    return web.Response(text="""
    <!DOCTYPE html>
    <html><head><meta charset='utf-8'><title>Вход</title>
    <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', Arial; background:#f5f5f7; margin:0; }
    .wrap { max-width:380px; margin:80px auto; background:#fff; padding:24px; border-radius:18px; box-shadow:0 8px 30px rgba(0,0,0,0.06); }
    label{display:block;margin:8px 0 6px;font-weight:600}
    input{width:100%;padding:10px 12px;border:1px solid #e5e5ea;border-radius:12px}
    button{background:#0071e3;color:#fff;border:none;border-radius:999px;padding:10px 16px;margin-top:12px;cursor:pointer}
    a{text-decoration:none;color:#0071e3}
    </style></head>
    <body><div class='wrap'>
    <h2>Вход</h2>
    <form method='post' action='/login'>
    <label>Логин</label><input name='username' required>
    <label>Пароль</label><input name='password' type='password' required>
    <button type='submit'>Войти</button>
    <p>Нет аккаунта? <a href='/register'>Регистрация</a></p>
    </form></div></body></html>
    """, content_type='text/html')

async def login_post(request: Request) -> Response:
    data = await request.post()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    users = await users_storage.read_all()
    user = next((u for u in users if u.get('username') == username), None)
    if not user or not await verify_password(password, user.get('password_hash', '')):
        return web.Response(text="Неверные учетные данные", status=401)
    
    # Store user in memory (simple auth)
    from auth import _current_users
    _current_users[username] = {'username': user['username'], 'role': user.get('role', 'user')}
    
    # Redirect with user token
    raise web.HTTPFound(f'/?user={username}')

async def register_page(request: Request) -> Response:
    return web.Response(text="""
    <!DOCTYPE html>
    <html><head><meta charset='utf-8'><title>Регистрация</title>
    <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', Arial; background:#f5f5f7; margin:0; }
    .wrap { max-width:380px; margin:80px auto; background:#fff; padding:24px; border-radius:18px; box-shadow:0 8px 30px rgba(0,0,0,0.06); }
    label{display:block;margin:8px 0 6px;font-weight:600}
    input{width:100%;padding:10px 12px;border:1px solid #e5e5ea;border-radius:12px}
    button{background:#0071e3;color:#fff;border:none;border-radius:999px;padding:10px 16px;margin-top:12px;cursor:pointer}
    </style></head>
    <body><div class='wrap'>
    <h2>Регистрация</h2>
    <form method='post' action='/register'>
    <label>Логин</label><input name='username' required>
    <label>Пароль</label><input name='password' type='password' required>
    <button type='submit'>Зарегистрироваться</button>
    </form></div></body></html>
    """, content_type='text/html')

async def register_post(request: Request) -> Response:
    data = await request.post()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return web.Response(text="Укажите логин и пароль", status=400)
    users = await users_storage.read_all()
    if any(u.get('username') == username for u in users):
        return web.Response(text="Пользователь уже существует", status=400)
    password_hash = await hash_password(password)
    users.append({'id': str(uuid.uuid4()), 'username': username, 'password_hash': password_hash, 'role': 'user', 'created_at': datetime.now().isoformat()})
    await users_storage.write_all(users)
    raise web.HTTPFound('/login')

async def logout(request: Request) -> Response:
    # Simple logout - clear user from memory
    from auth import _current_users
    user = await get_current_user(request)
    if user:
        username = user.get('username')
        if username in _current_users:
            del _current_users[username]
    raise web.HTTPFound('/')

@require_admin
async def admin_page(request: Request) -> Response:
    users = await users_storage.read_all()
    logs = await logs_storage.read_all()
    html = f"""
    <!DOCTYPE html><html><head><meta charset='utf-8'><title>Админ</title>
    <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', Arial; background:#f5f5f7; margin:0; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 32px; }}
    .card {{ background:#fff; border-radius:18px; box-shadow:0 8px 30px rgba(0,0,0,0.06); padding:20px; margin:12px 0; }}
    table {{ width:100%; border-collapse: collapse; }}
    th, td {{ text-align:left; padding:8px 6px; border-bottom:1px solid #eee; font-size:14px; }}
    </style></head><body>
    <div class='container'>
      <h2>Админ панель</h2>
      <div class='card'>
        <h3>Пользователи ({len(users)})</h3>
        <table><thead><tr><th>Логин</th><th>Роль</th><th>Создан</th></tr></thead><tbody>
        {''.join([f"<tr><td>{u.get('username')}</td><td>{u.get('role')}</td><td>{u.get('created_at')}</td></tr>" for u in users])}
        </tbody></table>
      </div>
      <div class='card'>
        <h3>Логи ({len(logs)})</h3>
        <table><thead><tr><th>Время</th><th>Метод</th><th>Путь</th><th>Статус</th><th>Пользователь</th><th>IP</th><th>Длительность, мс</th></tr></thead><tbody>
        {''.join([f"<tr><td>{l.get('ts')}</td><td>{l.get('method')}</td><td>{l.get('path')}</td><td>{l.get('status')}</td><td>{l.get('user')}</td><td>{l.get('ip')}</td><td>{l.get('duration_ms')}</td></tr>" for l in logs[-200:]])}
        </tbody></table>
      </div>
    </div>
    </body></html>
    """
    return web.Response(text=html, content_type='text/html')

def create_app() -> web.Application:
    """Создание приложения aiohttp"""
    app = web.Application()
    # No sessions - simple auth

    @web.middleware
    async def logging_middleware(request, handler):
        start = datetime.now()
        user = await get_current_user(request)
        try:
            response = await handler(request)
            status = response.status if isinstance(response, web.Response) else 200
            return response
        finally:
            entry = {
                'ts': datetime.now().isoformat(),
                'method': request.method,
                'path': request.path,
                'status': locals().get('status', 200),
                'user': (user.get('username') if user else None),
                'ip': request.remote,
                'duration_ms': int((datetime.now() - start).total_seconds() * 1000),
            }
            logs = await logs_storage.read_all()
            logs.append(entry)
            await logs_storage.write_all(logs)

    app.middlewares.append(logging_middleware)
    
    # Статические маршруты
    app.router.add_get('/', index)
    app.router.add_get('/resumes', resumes_page)
    app.router.add_get('/jobs', jobs_page)
    app.router.add_get('/analyses', analyses_page)
    
    # API маршруты
    app.router.add_post('/api/resumes', create_resume)
    app.router.add_get('/api/resumes', get_resumes)
    app.router.add_post('/api/jobs', create_job)
    app.router.add_get('/api/jobs', get_jobs)
    app.router.add_post('/api/analyze', analyze_resume)
    app.router.add_get('/api/analyses', get_analyses)
    app.router.add_post('/api/import/hh', import_hh_resume)
    
    # Auth routes
    app.router.add_get('/login', login_page)
    app.router.add_post('/login', login_post)
    app.router.add_get('/register', register_page)
    app.router.add_post('/register', register_post)
    app.router.add_get('/logout', logout)
    app.router.add_get('/admin', admin_page)
    
    return app

if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host=HOST, port=PORT)

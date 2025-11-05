# Система анализа релевантности резюме

Веб-приложение для анализа релевантности резюме кандидатов с использованием aiohttp и RAG (Retrieval-Augmented Generation).

## Возможности

- ✅ Управление резюме кандидатов
- ✅ Создание описаний вакансий  
- ✅ Автоматический анализ релевантности с помощью ИИ
- ✅ Просмотр результатов анализа
- ✅ Хранение данных в JSON файлах (без БД)
- ✅ Аутентификация (регистрация/вход/выход), роли (user/admin)
- ✅ Админ-панель: список пользователей и логов
- ✅ Логирование всех действий в `data/logs.json`

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` в корне проекта:
```env
OPENAI_API_KEY=your_openai_api_key_here
HOST=localhost
PORT=8080
DEBUG=True
```

3. Получите API ключ OpenAI на https://platform.openai.com/api-keys

## Запуск

```bash
python main.py
```

Приложение будет доступно по адресу: http://localhost:8080

## Запуск в Docker

Создайте образ и запустите контейнер:

```bash
docker build -t resumes-rag .
docker run --name resumes-rag -p 8080:8080 -e HOST=0.0.0.0 -v "$(pwd)/data:/app/data" resumes-rag
```

Или используйте docker-compose:

```bash
docker-compose up --build
```

Передайте ключ OpenAI через переменную окружения `OPENAI_API_KEY` (опционально) или файл `.env`.

## Структура проекта

```
├── main.py              # Основной файл приложения
├── models.py            # Модели данных (Pydantic)
├── storage.py           # Модуль для работы с JSON файлами
├── rag_analyzer.py      # RAG анализатор для ИИ
├── config.py            # Конфигурация приложения
├── requirements.txt     # Зависимости Python
├── data/               # Директория с JSON файлами
│   ├── resumes.json    # Резюме кандидатов
│   ├── analyses.json   # Результаты анализов
│   └── jobs.json       # Описания вакансий
└── README.md           # Документация
```

## API Endpoints

### Резюме
- `GET /api/resumes` - Получить все резюме
- `POST /api/resumes` - Создать новое резюме

### Вакансии
- `GET /api/jobs` - Получить все вакансии
- `POST /api/jobs` - Создать новую вакансию

### Анализ
- `POST /api/analyze` - Проанализировать релевантность резюме
- `GET /api/analyses` - Получить все анализы

### Импорт
- `POST /api/import/hh` - Импортировать резюме из JSON формата hh.ru

## Аутентификация и роли

- Страницы входа: `GET /login`, регистрация: `GET /register`, выход: `GET /logout`
- Сессии через cookie, пароли хранятся в виде хеша (bcrypt)
- Админ-панель: `GET /admin` (требуется роль admin)
- Пользователи хранятся в `data/users.json`

Примечание: создайте первого администратора вручную, либо отредактируйте `data/users.json`, изменив `role` на `admin` для нужного пользователя.

## Пример использования API

### Создание резюме
```bash
curl -X POST http://localhost:8080/api/resumes \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Иван Петров",
    "position": "Python Developer",
    "experience": 3,
    "skills": ["Python", "Django", "PostgreSQL"],
    "education": "Высшее техническое",
    "languages": ["Русский", "Английский"],
    "contact_info": {
      "email": "ivan@example.com",
      "phone": "+7-999-123-45-67"
    }
  }'
```

### Создание вакансии
```bash
curl -X POST http://localhost:8080/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Senior Python Developer",
    "requirements": ["Опыт работы 3+ лет", "Высшее образование"],
    "responsibilities": ["Разработка backend", "Code review"],
    "skills_required": ["Python", "Django", "PostgreSQL", "Docker"],
    "experience_required": 3
  }'
```

### Анализ релевантности
```bash
curl -X POST http://localhost:8080/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "resume_id": "resume_id_here",
    "job_id": "job_id_here"
  }'
```

## Особенности

- **Без базы данных**: Все данные хранятся в JSON файлах
- **RAG анализ**: Использует OpenAI GPT для анализа релевантности
- **Асинхронность**: Полностью асинхронное приложение на aiohttp
- **Веб-интерфейс**: Удобный веб-интерфейс для управления данными
- **API**: RESTful API для интеграции с другими системами
 - **Импорт с hh.ru**: Вставьте JSON резюме на странице `Резюме` для быстрого импорта

## Технологии

- **aiohttp** - Асинхронный веб-фреймворк
- **Pydantic** - Валидация данных
- **OpenAI API** - ИИ для анализа
- **aiofiles** - Асинхронная работа с файлами
- **Jinja2** - Шаблонизатор (для будущих улучшений)

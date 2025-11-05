import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Application settings
# Разрешаем переопределять через переменные окружения (для Docker/Prod)
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes")

# File paths
DATA_DIR = "data"
RESUMES_FILE = "resumes.json"
ANALYSES_FILE = "analyses.json"

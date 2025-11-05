import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes")

DATA_DIR = "data"
RESUMES_FILE = "resumes.json"
ANALYSES_FILE = "analyses.json"

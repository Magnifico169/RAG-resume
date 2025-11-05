from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class Resume(BaseModel):
    id: str
    name: str
    position: str
    experience: int
    skills: List[str]
    education: str
    languages: List[str]
    contact_info: Dict[str, str]
    created_at: datetime
    updated_at: datetime

class DateTimeEncoder(json.JSONEncoder):
    """Кастомный JSON encoder для обработки datetime"""
    def default(self, obj):
        if isinstance(obj, (datetime,)):
            return obj.isoformat()
        return super().default(obj)

class AnalysisResult(BaseModel):
    id: str
    resume_id: str
    relevance_score: float
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]
    job_match_percentage: float
    analysis_text: str
    created_at: datetime

    def json_serializable_dict(self) -> Dict[str, Any]:
        """Возвращает словарь, готовый для JSON сериализации"""
        return {
            'id': self.id,
            'resume_id': self.resume_id,
            'relevance_score': self.relevance_score,
            'strengths': self.strengths,
            'weaknesses': self.weaknesses,
            'recommendations': self.recommendations,
            'job_match_percentage': self.job_match_percentage,
            'analysis_text': self.analysis_text,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class JobDescription(BaseModel):
    id: str
    title: str
    requirements: List[str]
    responsibilities: List[str]
    skills_required: List[str]
    experience_required: int
    created_at: datetime



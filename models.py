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

class JobDescription(BaseModel):
    id: str
    title: str
    requirements: List[str]
    responsibilities: List[str]
    skills_required: List[str]
    experience_required: int
    created_at: datetime



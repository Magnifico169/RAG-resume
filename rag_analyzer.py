import openai
from typing import List, Dict, Any
import json
from config import OPENAI_API_KEY
from models import Resume, AnalysisResult, JobDescription
from datetime import datetime
import uuid

class RAGAnalyzer:
    def __init__(self):
        if OPENAI_API_KEY:
            openai.api_key = OPENAI_API_KEY
        else:
            print("Warning: OPENAI_API_KEY not set. RAG analysis will use mock data.")
    
    async def analyze_resume_relevance(self, resume: Resume, job_description: JobDescription) -> AnalysisResult:
        """Анализирует релевантность резюме для конкретной вакансии"""
        
        if not OPENAI_API_KEY:
            return self._create_mock_analysis(resume, job_description)
        
        try:
            # Подготавливаем контекст для анализа
            context = self._prepare_analysis_context(resume, job_description)
            
            # Создаем промпт для анализа
            prompt = self._create_analysis_prompt(resume, job_description)
            
            # Вызываем OpenAI API
            response = await self._call_openai_api(prompt)
            
            # Парсим ответ и создаем результат анализа
            analysis_data = self._parse_analysis_response(response)
            
            return AnalysisResult(
                id=str(uuid.uuid4()),
                resume_id=resume.id,
                relevance_score=analysis_data['relevance_score'],
                strengths=analysis_data['strengths'],
                weaknesses=analysis_data['weaknesses'],
                recommendations=analysis_data['recommendations'],
                job_match_percentage=analysis_data['job_match_percentage'],
                analysis_text=analysis_data['analysis_text'],
                created_at=datetime.now()
            )
            
        except Exception as e:
            print(f"Error in RAG analysis: {e}")
            return self._create_mock_analysis(resume, job_description)
    
    def _prepare_analysis_context(self, resume: Resume, job_description: JobDescription) -> str:
        """Подготавливает контекст для анализа"""
        context = f"""
        РЕЗЮМЕ:
        Имя: {resume.name}
        Позиция: {resume.position}
        Опыт работы: {resume.experience} лет
        Навыки: {', '.join(resume.skills)}
        Образование: {resume.education}
        Языки: {', '.join(resume.languages)}
        
        ВАКАНСИЯ:
        Название: {job_description.title}
        Требования: {', '.join(job_description.requirements)}
        Обязанности: {', '.join(job_description.responsibilities)}
        Необходимые навыки: {', '.join(job_description.skills_required)}
        Требуемый опыт: {job_description.experience_required} лет
        """
        return context
    
    def _create_analysis_prompt(self, resume: Resume, job_description: JobDescription) -> str:
        """Создает промпт для анализа"""
        return f"""
        Проанализируй релевантность резюме кандидата для указанной вакансии.
        
        РЕЗЮМЕ:
        Имя: {resume.name}
        Позиция: {resume.position}
        Опыт работы: {resume.experience} лет
        Навыки: {', '.join(resume.skills)}
        Образование: {resume.education}
        Языки: {', '.join(resume.languages)}
        
        ВАКАНСИЯ:
        Название: {job_description.title}
        Требования: {', '.join(job_description.requirements)}
        Обязанности: {', '.join(job_description.responsibilities)}
        Необходимые навыки: {', '.join(job_description.skills_required)}
        Требуемый опыт: {job_description.experience_required} лет
        
        Пожалуйста, предоставь анализ в следующем JSON формате:
        {{
            "relevance_score": 0.85,
            "strengths": ["сильная сторона 1", "сильная сторона 2"],
            "weaknesses": ["слабая сторона 1", "слабая сторона 2"],
            "recommendations": ["рекомендация 1", "рекомендация 2"],
            "job_match_percentage": 85,
            "analysis_text": "Подробный анализ релевантности..."
        }}
        """
    
    async def _call_openai_api(self, prompt: str) -> str:
        """Вызывает OpenAI API"""
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты эксперт по анализу резюме и подбору персонала. Отвечай только в JSON формате."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        return response.choices[0].message.content
    
    def _parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Парсит ответ от OpenAI"""
        try:
            # Извлекаем JSON из ответа
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            json_str = response[start_idx:end_idx]
            
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing analysis response: {e}")
            return self._get_default_analysis()
    
    def _create_mock_analysis(self, resume: Resume, job_description: JobDescription) -> AnalysisResult:
        """Создает мок-анализ для тестирования"""
        # Простая логика для мок-анализа
        skills_match = len(set(resume.skills) & set(job_description.skills_required))
        total_required_skills = len(job_description.skills_required)
        skill_match_percentage = (skills_match / max(total_required_skills, 1)) * 100
        
        experience_match = min(resume.experience / max(job_description.experience_required, 1), 1.0)
        
        overall_score = (skill_match_percentage + experience_match * 100) / 200
        
        return AnalysisResult(
            id=str(uuid.uuid4()),
            resume_id=resume.id,
            relevance_score=round(overall_score, 2),
            strengths=[
                f"Соответствие навыков: {skills_match}/{total_required_skills}",
                f"Опыт работы: {resume.experience} лет"
            ],
            weaknesses=[
                "Требуется дополнительная оценка soft skills",
                "Необходимо проверить соответствие образования"
            ],
            recommendations=[
                "Провести техническое интервью",
                "Оценить мотивацию кандидата"
            ],
            job_match_percentage=round(overall_score * 100, 1),
            analysis_text=f"Кандидат {resume.name} имеет {skills_match} из {total_required_skills} требуемых навыков и {resume.experience} лет опыта работы.",
            created_at=datetime.now()
        )
    
    def _get_default_analysis(self) -> Dict[str, Any]:
        """Возвращает анализ по умолчанию"""
        return {
            "relevance_score": 0.5,
            "strengths": ["Требуется дополнительный анализ"],
            "weaknesses": ["Не удалось провести полный анализ"],
            "recommendations": ["Провести ручную оценку"],
            "job_match_percentage": 50,
            "analysis_text": "Анализ не удалось завершить автоматически."
        }





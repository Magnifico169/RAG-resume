import openai
from typing import List, Dict, Any, Optional, Callable, Tuple, TypeVar, Awaitable
from dataclasses import dataclass
from functools import wraps, reduce
import json
from config import OPENAI_API_KEY
from models import Resume, AnalysisResult, JobDescription
from datetime import datetime
import uuid
import logging


logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U')
AnalysisData = Dict[str, Any]


@dataclass(frozen=True)
class AnalysisContext:
    """Иммутабельный контекст анализа"""
    resume: Resume
    job_description: JobDescription
    context_text: str = ""
    prompt: str = ""
    raw_response: str = ""
    parsed_data: Optional[AnalysisData] = None


@dataclass
class AnalysisResultM:
    """Монадический результат анализа"""
    context: Optional[AnalysisContext] = None
    result: Optional[AnalysisResult] = None
    error: Optional[Exception] = None

    def is_success(self) -> bool:
        return self.result is not None and self.error is None

    def map(self, func: Callable[[AnalysisResult], T]) -> 'AnalysisResultM':
        """Functor map"""
        if self.result and not self.error:
            try:
                return AnalysisResultM(result=func(self.result), context=self.context)
            except Exception as e:
                logger.error(f"Map operation failed: {e}")
                return AnalysisResultM(error=e, context=self.context)
        return self

    def bind(self, func: Callable[[AnalysisResult], 'AnalysisResultM']) -> 'AnalysisResultM':
        """Monadic bind для синхронных операций"""
        if self.result and not self.error:
            return func(self.result)
        return self

    async def bind_async(self, func: Callable[['AnalysisResultM'], Awaitable['AnalysisResultM']]) -> 'AnalysisResultM':
        """Monadic bind для асинхронных операций"""
        if self.error:
            return self
        try:
            return await func(self)
        except Exception as e:
            logger.error(f"Async bind failed: {e}")
            return AnalysisResultM(error=e, context=self.context)

    def fold(self, success_func: Callable[[AnalysisResult], T], error_func: Callable[[Exception], T]) -> T:
        """Catamorphism для извлечения результата"""
        if self.result and not self.error:
            return success_func(self.result)
        return error_func(self.error) if self.error else error_func(Exception("Unknown error"))


class Maybe:
    """Maybe монада для безопасной обработки значений"""

    def __init__(self, value: Optional[T]):
        self.value = value

    def map(self, func: Callable[[T], U]) -> 'Maybe':
        """Применяет функцию к значению если оно существует"""
        if self.value is not None:
            try:
                return Maybe(func(self.value))
            except Exception:
                return Maybe(None)
        return self

    async def bind_async(self, func: Callable[[T], Awaitable['Maybe']]) -> 'Maybe':
        """Асинхронная цепочка операций"""
        if self.value is not None:
            return await func(self.value)
        return self

    def bind(self, func: Callable[[T], 'Maybe']) -> 'Maybe':
        """Цепочка операций"""
        if self.value is not None:
            return func(self.value)
        return self

    def or_else(self, default: T) -> T:
        """Возвращает значение или значение по умолчанию"""
        return self.value if self.value is not None else default


def prepare_analysis_context(resume: Resume, job_description: JobDescription) -> AnalysisContext:
    """Чистая функция подготовки контекста"""
    context_text = f"""
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

    prompt = create_analysis_prompt(resume, job_description)

    return AnalysisContext(
        resume=resume,
        job_description=job_description,
        context_text=context_text,
        prompt=prompt
    )


def create_analysis_prompt(resume: Resume, job_description: JobDescription) -> str:
    """Чистая функция создания промпта"""
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


def calculate_mock_analysis(resume: Resume, job_description: JobDescription) -> AnalysisData:
    """Чистая функция расчета мок-анализа"""
    skills_match = len(set(resume.skills) & set(job_description.skills_required))
    total_required_skills = max(len(job_description.skills_required), 1)
    skill_match_percentage = (skills_match / total_required_skills) * 100

    experience_match = min(resume.experience / max(job_description.experience_required, 1), 1.0)

    overall_score = (skill_match_percentage + experience_match * 100) / 200

    return {
        "relevance_score": round(overall_score, 2),
        "strengths": [
            f"Соответствие навыков: {skills_match}/{total_required_skills}",
            f"Опыт работы: {resume.experience} лет"
        ],
        "weaknesses": [
            "Требуется дополнительная оценка soft skills",
            "Необходимо проверить соответствие образования"
        ],
        "recommendations": [
            "Провести техническое интервью",
            "Оценить мотивацию кандидата"
        ],
        "job_match_percentage": round(overall_score * 100, 1),
        "analysis_text": f"Кандидат {resume.name} имеет {skills_match} из {total_required_skills} требуемых навыков и {resume.experience} лет опыта работы."
    }


def get_default_analysis() -> AnalysisData:
    """Чистая функция возврата анализа по умолчанию"""
    return {
        "relevance_score": 0.5,
        "strengths": ["Требуется дополнительный анализ"],
        "weaknesses": ["Не удалось провести полный анализ"],
        "recommendations": ["Провести ручную оценку"],
        "job_match_percentage": 50,
        "analysis_text": "Анализ не удалось завершить автоматически."
    }


def create_analysis_result_from_data(data: AnalysisData, resume: Resume) -> AnalysisResult:
    """Чистая функция создания AnalysisResult из данных"""
    return AnalysisResult(
        id=str(uuid.uuid4()),
        resume_id=resume.id,
        relevance_score=data['relevance_score'],
        strengths=data['strengths'],
        weaknesses=data['weaknesses'],
        recommendations=data['recommendations'],
        job_match_percentage=data['job_match_percentage'],
        analysis_text=data['analysis_text'],
        created_at=datetime.now()
    )


def create_mock_analysis_result(resume: Resume, job_description: JobDescription) -> AnalysisResult:
    """Чистая функция создания мок-анализа"""
    analysis_data = calculate_mock_analysis(resume, job_description)
    return create_analysis_result_from_data(analysis_data, resume)


def parse_response_safe(response: str) -> Maybe[AnalysisData]:
    """Чистая функция безопасного парсинга ответа"""
    try:
        logger.debug(f"Parsing response: {response[:200]}...")

        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1

        if start_idx == -1 or end_idx == 0:
            logger.warning("No JSON found in response")
            return Maybe(None)

        json_str = response[start_idx:end_idx]
        logger.debug(f"Extracted JSON: {json_str[:200]}...")

        parsed_data = json.loads(json_str)
        logger.info(f"Successfully parsed analysis response: {list(parsed_data.keys())}")

        return Maybe(parsed_data)
    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        logger.error(f"Response parsing failed: {e}")
        return Maybe(None)


# Композиция функций
def compose(*functions: Callable) -> Callable:
    """Композиция функций"""
    return reduce(lambda f, g: lambda x: g(f(x)), functions)


async def async_compose(*functions: Callable[[T], Awaitable[U]]) -> Callable[[T], Awaitable[U]]:
    """Композиция асинхронных функций"""
    async def composed(x: T) -> U:
        result = x
        for func in functions:
            result = await func(result)
        return result
    return composed


def with_analysis_logging(func: Callable) -> Callable:
    """Декоратор для логирования процесса анализа"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info(f"Starting analysis: {func.__name__}")
        start_time = datetime.now()

        try:
            result = await func(*args, **kwargs)
            duration = (datetime.now() - start_time).total_seconds()

            if hasattr(result, 'fold'):
                result.fold(
                    success_func=lambda res: logger.info(
                        f"Analysis completed successfully in {duration:.2f}s. "
                        f"Relevance: {getattr(res, 'relevance_score', 'N/A')}, "
                        f"Match: {getattr(res, 'job_match_percentage', 'N/A')}%"
                    ),
                    error_func=lambda e: logger.error(
                        f"Analysis failed after {duration:.2f}s: {e}"
                    )
                )
            else:
                logger.info(f"Analysis completed in {duration:.2f}s")

            return result

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Analysis crashed after {duration:.2f}s: {e}")
            raise

    return wrapper


class RAGAnalyzer:
    def __init__(self, use_mock: Optional[bool] = None):
        """Инициализация анализатора
        
        Args:
            use_mock: Если True, использует мок-анализ. Если None, определяется автоматически по наличию API ключа
        """
        self.use_mock = use_mock if use_mock is not None else not OPENAI_API_KEY
        if OPENAI_API_KEY:
            openai.api_key = OPENAI_API_KEY
            logger.info("OpenAI API key configured")
        else:
            logger.warning("OPENAI_API_KEY not set. RAG analysis will use mock data.")

    @with_analysis_logging
    async def analyze_resume_relevance(self, resume: Resume, job_description: JobDescription) -> AnalysisResult:
        """Анализирует релевантность резюме для конкретной вакансии
        
        Функциональный pipeline:
        1. Подготовка контекста
        2. Анализ с RAG (или мок)
        3. Создание результата
        
        Все шаги объединены через монадические bind операции.
        """
        logger.info(f"Starting analysis for resume: {resume.name}, job: {job_description.title}")

        initial_result = await self._prepare_context_safe((resume, job_description))


        analysis_result = await self._analyze_with_rag_safe(initial_result)

        final_result = await self._create_analysis_result_safe(analysis_result)

        return final_result.fold(
            success_func=lambda result: result,
            error_func=lambda e: self._handle_error(e, resume, job_description)
        )

    async def _prepare_context_safe(self, data: Tuple[Resume, JobDescription]) -> AnalysisResultM:
        """Безопасная подготовка контекста анализа (функциональный подход)"""
        resume, job_description = data
        try:
            logger.debug(f"Preparing context for resume: {resume.id}, job: {job_description.id}")
            context = prepare_analysis_context(resume, job_description)
            logger.debug("Context preparation completed")
            return AnalysisResultM(context=context)
        except Exception as e:
            logger.error(f"Context preparation failed: {e}")
            return AnalysisResultM(error=e)

    async def _analyze_with_rag_safe(self, result: AnalysisResultM) -> AnalysisResultM:
        """Безопасный анализ с использованием RAG (функциональный подход)"""
        if result.error or not result.context:
            logger.warning(f"Skipping RAG analysis due to error: {result.error}")
            return result

        if self.use_mock:
            logger.info("Using mock analysis (no API key)")
            return await self._mock_analysis_safe(result.context)

        try:
            logger.info("Calling OpenAI API for analysis")
            prompt = result.context.prompt

            api_response_maybe = await self._call_openai_api_safe(prompt)

            if api_response_maybe.value is None:
                logger.warning("OpenAI API returned None, using default")
                analysis_data = get_default_analysis()
            else:
                parse_result = parse_response_safe(api_response_maybe.value)
                analysis_data = parse_result.or_else(get_default_analysis())

            logger.debug(f"Analysis data received: {list(analysis_data.keys()) if isinstance(analysis_data, dict) else 'not dict'}")

            updated_context = AnalysisContext(
                resume=result.context.resume,
                job_description=result.context.job_description,
                context_text=result.context.context_text,
                prompt=result.context.prompt,
                parsed_data=analysis_data
            )

            return AnalysisResultM(context=updated_context)

        except Exception as e:
            logger.error(f"RAG analysis failed: {e}")
            return AnalysisResultM(error=e, context=result.context)

    async def _call_openai_api_safe(self, prompt: str) -> Maybe[str]:
        """Безопасный вызов OpenAI API (чистая функция с побочными эффектами)"""
        try:
            logger.debug(f"Calling OpenAI API with prompt length: {len(prompt)}")

            client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system",
                     "content": "Ты эксперт по анализу резюме и подбору персонала. Отвечай только в JSON формате."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )

            content = response.choices[0].message.content
            logger.debug(f"OpenAI response received, length: {len(content) if content else 0}")

            return Maybe(content)
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return Maybe(None)

    async def _mock_analysis_safe(self, context: AnalysisContext) -> AnalysisResultM:
        """Безопасный мок-анализ (функциональный подход)"""
        try:
            logger.info("Performing mock analysis")
            analysis_data = calculate_mock_analysis(context.resume, context.job_description)

            updated_context = AnalysisContext(
                resume=context.resume,
                job_description=context.job_description,
                context_text=context.context_text,
                prompt=context.prompt,
                parsed_data=analysis_data
            )

            return AnalysisResultM(context=updated_context)
        except Exception as e:
            logger.error(f"Mock analysis failed: {e}")
            return AnalysisResultM(error=e, context=context)

    async def _create_analysis_result_safe(self, result: AnalysisResultM) -> AnalysisResultM:
        """Безопасное создание финального результата анализа (функциональный подход)"""
        if result.error or not result.context or not result.context.parsed_data:
            logger.error(
                f"Cannot create analysis result: error={result.error}, "
                f"context={result.context is not None}, "
                f"data={result.context.parsed_data is not None if result.context else False}"
            )
            return result

        try:
            data = result.context.parsed_data
            resume = result.context.resume

            logger.debug(f"Creating AnalysisResult from data: {data}")

            analysis_result = create_analysis_result_from_data(data, resume)

            logger.info(f"Analysis result created: ID={analysis_result.id}, Score={analysis_result.relevance_score}")

            return AnalysisResultM(result=analysis_result, context=result.context)
        except Exception as e:
            logger.error(f"Failed to create analysis result: {e}")
            return AnalysisResultM(error=e, context=result.context)

    def _handle_error(self, error: Exception, resume: Resume, job_description: JobDescription) -> AnalysisResult:
        """Обработка ошибки с возвратом мок-анализа (fallback)"""
        logger.warning(f"Analysis failed, using mock analysis as fallback: {error}")
        return create_mock_analysis_result(resume, job_description)

from collections.abc import AsyncIterator

import groq
import structlog

from app.core.config import get_settings
from app.models.application import Application
from app.models.cv import Cv

logger = structlog.get_logger()


def _get_client() -> groq.AsyncGroq:
    settings = get_settings()
    return groq.AsyncGroq(api_key=settings.GROQ_API_KEY)


def build_system_prompt(application: Application, cv: Cv | None) -> str:
    """Build a system prompt from application and optional CV context."""
    parts = [
        "You are a helpful career assistant for a job seeker. "
        "You have access to the following context about a specific job application. "
        "Provide specific, actionable advice tailored to this role and company. "
        "Be concise and professional.",
        "",
        "**Application:**",
        f"- Company: {application.company_name}",
        f"- Role: {application.role_title}",
    ]

    if application.job_url:
        parts.append(f"- Job URL: {application.job_url}")
    if application.status:
        parts.append(f"- Status: {application.status}")
    if application.notes:
        parts.append(f"- Notes: {application.notes}")

    if cv:
        parts.append("")
        parts.append(f"**Candidate's CV ({cv.name}):**")

        if cv.personal_info:
            info = cv.personal_info
            name = info.get("full_name", "")
            if name:
                parts.append(f"- Name: {name}")

        if cv.summary:
            parts.append(f"- Summary: {cv.summary}")

        if cv.work_experience:
            parts.append("- Work Experience:")
            for exp in cv.work_experience:
                end = "Present" if exp.get("is_current") else exp.get("end_date", "")
                parts.append(
                    f"  - {exp.get('role', '')} at {exp.get('company', '')} "
                    f"({exp.get('start_date', '')} — {end})"
                )
                if exp.get("description"):
                    parts.append(f"    {exp['description']}")

        if cv.education:
            parts.append("- Education:")
            for edu in cv.education:
                parts.append(
                    f"  - {edu.get('degree', '')} in {edu.get('field_of_study', '')} "
                    f"at {edu.get('institution', '')} "
                    f"({edu.get('start_year', '')} — {edu.get('end_year', '')})"
                )

        if cv.skills:
            parts.append(f"- Skills: {cv.skills}")

        if cv.languages:
            parts.append(f"- Languages: {cv.languages}")

    return "\n".join(parts)


async def stream_llm_response(
    system_prompt: str,
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Stream the LLM's response, yielding text chunks."""
    settings = get_settings()
    client = _get_client()

    full_messages = [
        {"role": "system", "content": system_prompt},
        *messages,
    ]

    try:
        stream = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            max_tokens=4096,
            messages=full_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except groq.AuthenticationError as e:
        logger.error("Groq authentication error", error=str(e))
        raise RuntimeError(
            "AI service authentication failed. Please contact the operator."
        ) from e
    except groq.RateLimitError as e:
        logger.error("Groq rate limit", error=str(e))
        raise RuntimeError(
            "Rate limit reached. Please try again in a moment."
        ) from e
    except groq.APIConnectionError as e:
        logger.error("Groq connection error", error=str(e))
        raise RuntimeError(
            "Couldn't reach the AI service. Please try again."
        ) from e
    except groq.APIError as e:
        logger.error("Groq API error", error=str(e))
        raise

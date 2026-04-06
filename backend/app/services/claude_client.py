from collections.abc import AsyncIterator

import anthropic
import structlog

from app.core.config import get_settings
from app.models.application import Application
from app.models.cv import Cv

logger = structlog.get_logger()


def _get_client() -> anthropic.AsyncAnthropic:
    settings = get_settings()
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


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


async def stream_claude_response(
    system_prompt: str,
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Stream Claude's response, yielding text chunks."""
    settings = get_settings()
    client = _get_client()

    try:
        async with client.messages.stream(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except anthropic.APIError as e:
        logger.error("Anthropic API error", error=str(e))
        raise

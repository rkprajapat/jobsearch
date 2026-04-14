from datetime import datetime, timezone

from agents.resume_builder.agent import _RESUME_PATH
from agents.resume_builder.resume_state import ResumeState, TimeAwareStatus
from services.generator import generate_response
from utils import get_logger

logger = get_logger(__name__)

_HEADER_PROMPT = """\
You are a professional resume writer. Extract only the contact header from the resume text below.

Include ONLY:
- Candidate full name (first line)
- Email address
- Phone number
- Professional web links (LinkedIn, GitHub, portfolio, etc.)

Do NOT include:
- Degrees, diplomas, or any educational history
- Institutions, universities, or schools
- Dates or years of any kind
- Summaries, titles, or any other content

Return the header as plain text only. No markdown. No labels like "Email:" unless present in the resume.

RESUME TEXT:
{resume}

Omit any field not found in the resume. Return an empty string if nothing relevant is found."""


def _is_header_current(state: ResumeState) -> bool:
    file_mdate = datetime.fromtimestamp(
        _RESUME_PATH.stat().st_mtime, tz=timezone.utc
    ).date()
    logger.debug(
        "Checking if header is current: file modified on %s, state last updated on %s",
        file_mdate,
        state.header.last_updated.date(),
    )
    is_current = (
        state.header.status == "Completed"
        and state.header.last_updated.date() >= file_mdate
    )
    logger.debug("Header current status: %s", is_current)
    return is_current


def _build_header(state: ResumeState) -> None:
    if not _RESUME_PATH.exists():
        raise FileNotFoundError(f"Resume file not found at {_RESUME_PATH}")

    if _is_header_current(state):
        logger.info("Header is current — skipping rebuild")
        return

    logger.info("Building header section")
    state.header.mark_in_progress()
    resume_text = _RESUME_PATH.read_text(encoding="utf-8")
    header_content = generate_response(_HEADER_PROMPT.format(resume=resume_text))

    if not header_content.strip():
        state.header.mark_failed()
        logger.error("Header generation returned empty content")
        return

    state.header.complete(header_content)
    logger.info("Header section completed successfully")


def _collect_failures(state: ResumeState) -> list[str]:
    return [
        name
        for name, value in vars(state).items()
        if isinstance(value, TimeAwareStatus) and value.status == "Failed"
    ]


def build_sections() -> bool:
    state = ResumeState.load()
    _build_header(state)
    state.save()
    failures = _collect_failures(state)
    if failures:
        logger.warning("Section build completed with failures: %s", failures)
    else:
        logger.info("All sections built successfully")
    return not failures


if __name__ == "__main__":
    build_sections()

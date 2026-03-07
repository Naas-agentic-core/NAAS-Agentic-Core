"""
Retrieval Service Orchestrator.
Application Layer.
Coordinators domain logic, infrastructure, and fallback strategies.
"""


import contextlib

from microservices.orchestrator_service.src.core.logging import get_logger

logger = get_logger("tool-retrieval-service")


def _calculate_year_penalty(payload_year: str | int | None, requested_year: str | None) -> int:
    """
    Calculates penalty for year mismatch.
    0: Exact Match
    1: Missing Year (Soft Penalty)
    3: Explicit Mismatch (Hard Penalty)
    """
    if not requested_year:
        return 0

    if payload_year is None or str(payload_year).strip() == "":
        return 1

    if str(payload_year) == str(requested_year):
        return 0

    return 3


async def search_educational_content(
    query: str,
    year: str | None = None,
    subject: str | None = None,
    branch: str | None = None,
    exam_ref: str | None = None,
    exercise_id: str | None = None,
) -> str:
    from microservices.orchestrator_service.src.services.tools.content import search_content

    # Try converting year to int
    year_int = None
    if year:
        with contextlib.suppress(ValueError):
            year_int = int(year)

    # Add exercise_id to query if present
    full_query = query
    if exercise_id:
        full_query = f"{query} {exercise_id}"

    results = await search_content(
        q=full_query, year=year_int, subject=subject, branch=branch, set_name=exam_ref
    )

    if not results:
        return "لم يتم العثور على نتائج."

    return results[0].get("content", "لم يتم العثور على محتوى متوافق.")

"""
أدوات إدارة المحتوى التعليمي (Content Tools).

تتيح للوكلاء:
1. استكشاف هيكلة المنهج (Subject -> Branch -> Topic).
2. البحث عن تمارين ومحتوى باستخدام الفلاتر.
3. استرجاع المحتوى الخام (Raw Content) والحلول الرسمية.
"""

import difflib
import json

from app.core.logging import get_logger
from app.domain.constants import BRANCH_MAP
from app.infrastructure.clients.research_client import research_client
from app.services.chat.tools.schemas import SearchContentSchema

logger = get_logger("content-tools")

_BRANCH_LABELS: dict[str, str] = {
    "experimental_sciences": "علوم تجريبية",
    "math_tech": "تقني رياضي",
    "mathematics": "رياضيات",
    "foreign_languages": "لغات أجنبية",
    "literature_philosophy": "آداب وفلسفة",
}


def _scan_for_error(data: object) -> str | None:
    """يبحث بشكل عميق عن أي مفاتيح خطأ."""
    if isinstance(data, dict):
        if data.get("type") == "error":
            return str(data.get("content") or data.get("error") or "Unknown Error")
        return next((err for v in data.values() if (err := _scan_for_error(v))), None)

    if isinstance(data, list):
        return next((err for item in data if (err := _scan_for_error(item))), None)

    if isinstance(data, str) and '"type": "error"' in data:
        try:
            if data.strip().startswith("{"):
                return _scan_for_error(json.loads(data))
        except json.JSONDecodeError:
            pass

    return None


def _normalize_branch(value: str | None) -> str | None:
    """توحيد اسم الشعبة باستخدام منطق الخدمة الموحد."""
    if not value:
        return None

    normalized = value.strip().lower()
    for key, variants in BRANCH_MAP.items():
        if normalized in variants:
            return _BRANCH_LABELS.get(key, key)

    reverse_map: dict[str, str] = {}
    all_variants: list[str] = []
    for key, variants in BRANCH_MAP.items():
        for variant in variants:
            reverse_map[variant] = key
            all_variants.append(variant)

    matches = difflib.get_close_matches(normalized, all_variants, n=1, cutoff=0.6)
    if matches:
        return _BRANCH_LABELS.get(reverse_map[matches[0]], reverse_map[matches[0]])

    for variant in all_variants:
        if len(variant) > 3 and variant in normalized:
            return _BRANCH_LABELS.get(reverse_map[variant], reverse_map[variant])

    return value


async def get_curriculum_structure(
    level: str | None = None,
    lang: str = "ar",
) -> dict[str, object]:
    """جلب شجرة المنهج الدراسي بالكامل أو لمستوى محدد."""
    try:
        return await research_client.get_curriculum_structure(level)
    except Exception as e:
        logger.error(f"Failed to fetch curriculum structure: {e}")
        return {}


async def search_content(
    q: str | None = None,
    level: str | None = None,
    subject: str | None = None,
    branch: str | None = None,
    set_name: str | None = None,
    year: int | None = None,
    type: str | None = None,
    lang: str | None = None,
    limit: int = 10,
    **kwargs,
) -> list[dict[str, object]]:
    """
    Cognitive Research Infrastructure (CRI).
    Advanced deep-research engine. Use this for ALL information retrieval.
    It performs multi-step reasoning, scraping, and fact-checking using
    autonomous agents (Tavily/Firecrawl).
    Returns a detailed research report.
    """

    # --- Layer A: Schema Adapter & Validation ---
    try:
        # Create a dictionary of all arguments provided
        # Filter out None values so Pydantic can use aliases (e.g. 'query') from kwargs
        # without conflict from the default 'q=None'
        explicit_args = {
            "q": q,
            "level": level,
            "subject": subject,
            "branch": branch,
            "set_name": set_name,
            "year": year,
            "type": type,
            "lang": lang,
            "limit": limit,
        }
        filtered_args = {k: v for k, v in explicit_args.items() if v is not None}

        # Merge with kwargs (kwargs take precedence if conflict, though usually they fill gaps)
        # CRITICAL FIX: Gracefully absorb unknown args from LLM hallucination
        raw_args = {**filtered_args, **kwargs}

        # Log unexpected args for debugging but don't crash
        known_keys = set(explicit_args.keys()) | {"query"}
        unexpected = set(raw_args.keys()) - known_keys
        if unexpected:
            logger.warning(f"search_content received unexpected args (ignored): {unexpected}")

        # Validate against the Pydantic Schema (Adapts aliases like 'query' -> 'q')
        validated_data = SearchContentSchema(**raw_args)

        # Use validated data
        q = validated_data.q
        level = validated_data.level
        subject = validated_data.subject
        branch = validated_data.branch
        set_name = validated_data.set_name
        year = validated_data.year
        type = validated_data.type
        lang = validated_data.lang
        limit = validated_data.limit

    except Exception as e:
        logger.error(f"Schema Validation Failed in search_content: {e}")
        # Strict Fail-Fast Policy (RFC 001)
        # We must propagate exceptions to the TaskExecutor to ensure honest outcome reporting.
        raise e

    # ---------------------------------------------

    if not q:
        return []

    # Normalize branch if provided
    normalized_branch = _normalize_branch(branch) if branch else branch

    # Build query context
    context_parts = []
    if subject:
        context_parts.append(f"Subject: {subject}")
    if normalized_branch:
        context_parts.append(f"Branch: {normalized_branch}")
    if year:
        context_parts.append(f"Year: {year}")
    if level:
        context_parts.append(f"Level: {level}")
    if type:
        context_parts.append(f"Type: {type}")

    full_query = q
    if context_parts:
        full_query += f" ({', '.join(context_parts)})"

    # Direct execution to enforce Fail-Fast (Fixes Root Cause D)
    # Exceptions propagate to TaskExecutor -> Mission Status FAILED
    report = await research_client.deep_research(full_query)

    # 🛑 Strict Validation: Detect "Soft Failures" (Error-as-Data Anti-Pattern)
    # recursive check for error objects inside list/dict structures
    error_found = _scan_for_error(report)
    if error_found:
        raise ValueError(f"Research Tool Error: {error_found}")

    return [
        {
            "id": "research_report",
            "title": f"Research Report: {q}",
            "content": report,
            "type": "report",
            "metadata": {"query": full_query, "source": "SuperSearchOrchestrator"},
        }
    ]


async def get_content_raw(
    content_id: str, *, include_solution: bool = True
) -> dict[str, str] | None:
    """جلب النص الخام (Markdown) لتمرين أو درس معين مع خيار الحل."""
    try:
        return await research_client.get_content_raw(content_id, include_solution=include_solution)
    except Exception as e:
        logger.error(f"Get content raw failed: {e}")
        return None


async def get_solution_raw(content_id: str) -> dict[str, object] | None:
    """جلب الحل الرسمي (Official Solution) لتمرين."""
    data = await research_client.get_content_raw(content_id, include_solution=True)
    if data and "solution" in data:
        return {
            "solution_md": data["solution"],
        }
    return None


def register_content_tools(registry: dict) -> None:
    """
    Register content tools into the provided registry.
    """
    registry["search_content"] = search_content
    registry["get_content_raw"] = get_content_raw
    registry["get_solution_raw"] = get_solution_raw
    registry["get_curriculum_structure"] = get_curriculum_structure

    logger.info("Content tools registered successfully in agent registry")

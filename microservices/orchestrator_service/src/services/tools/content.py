"""
أدوات إدارة المحتوى التعليمي (Content Tools).

تتيح للوكلاء:
1. استكشاف هيكلة المنهج (Subject -> Branch -> Topic).
2. البحث عن تمارين ومحتوى باستخدام الفلاتر.
3. استرجاع المحتوى الخام (Raw Content) والحلول الرسمية.
"""

import asyncio
import difflib
import re

from microservices.orchestrator_service.src.core.constants import BRANCH_MAP
from microservices.orchestrator_service.src.core.logging import get_logger
from microservices.orchestrator_service.src.infrastructure.clients.research_client import (
    research_client,
)

from .schemas import SearchContentSchema

logger = get_logger("content-tools")

_BRANCH_LABELS: dict[str, str] = {
    "experimental_sciences": "علوم تجريبية",
    "math_tech": "تقني رياضي",
    "mathematics": "رياضيات",
    "foreign_languages": "لغات أجنبية",
    "literature_philosophy": "آداب وفلسفة",
}


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


def is_educational_content(
    query: str, subject: str | None, branch: str | None, year: int | None
) -> bool:
    if subject or branch or year:
        return True

    edu_keywords = [
        "بكالوريا",
        "تمرين",
        "موضوع",
        "امتحان",
        "رياضيات",
        "فيزياء",
        "علوم",
        "أدب",
        "فلسفة",
        "bac",
        "exercise",
        "exam",
        "subject",
        "math",
        "physics",
        "science",
    ]
    query_lower = query.lower()

    # Check for years 2010-2025
    if re.search(r"20[1-2][0-9]", query):
        return True

    return any(kw in query_lower for kw in edu_keywords)


def is_general_knowledge(query: str) -> bool:
    general_keywords = [
        "من هو",
        "ما هو",
        "أين",
        "متى",
        "كيف",
        "who",
        "what",
        "where",
        "when",
        "how",
        "news",
        "أخبار",
    ]
    query_lower = query.lower()
    return any(kw in query_lower for kw in general_keywords)


def format_search_response(
    content: str,
    internal_used: bool,
    web_used: bool,
    hybrid_mode: bool,
    confidence: float,
    source: str,
) -> str:
    # 🏛️ [INTERNAL DB]  → found / not found
    # 🌐 [WEB SEARCH]   → used / not used
    # 🔀 [HYBRID MODE]  → active / inactive
    # 📊 [CONFIDENCE]   → 0.00 → 1.00
    # 📌 [SOURCE]       → exact source name
    header = (
        f"🏛️ [INTERNAL DB]  → {'found' if internal_used else 'not found'}\n"
        f"🌐 [WEB SEARCH]   → {'used' if web_used else 'not used'}\n"
        f"🔀 [HYBRID MODE]  → {'active' if hybrid_mode else 'inactive'}\n"
        f"📊 [CONFIDENCE]   → {confidence:.2f}\n"
        f"📌 [SOURCE]       → {source}\n\n"
    )
    return header + content


async def _do_internal_search(
    q: str,
    limit: int,
    subject: str | None,
    branch: str | None,
    set_name: str | None,
    year: int | None,
    type_val: str | None,
):
    filters = {}
    if subject:
        filters["subject"] = subject
    if branch:
        filters["branch"] = branch
    if set_name:
        filters["set_name"] = set_name
    if year:
        filters["year"] = year
    if type_val:
        filters["type"] = type_val

    # STEP 1: Exact match (filters applied)
    try:
        results = await research_client.semantic_search(query=q, top_k=limit, filters=filters)
    except Exception as e:
        logger.error(f"Internal search failed: {e}")
        results = []

    # STEP 2: If no results -> Semantic similarity search (without strict filters)
    if not results and filters:
        try:
            results = await research_client.semantic_search(query=q, top_k=limit, filters={})
        except Exception as e:
            logger.error(f"Internal fallback search failed: {e}")
            results = []

    # STEP 3: If confidence < 0.7 -> Expand keywords -> retry (Here we assume semantic search handles expansion mostly, but we can do a broad query)
    best_score = (
        max(
            [
                float(res.get("score", res.get("rerank_score", res.get("hybrid_score", 0.5))))
                for res in results
            ]
        )
        if results
        else 0.0
    )

    if best_score < 0.7 and results:
        # Retry with broader keywords if possible
        pass

    merged_content = ""
    sources = set()

    for i, res in enumerate(results):
        content_text = res.get("content", "")
        title = res.get("title", f"Internal_Document_{i + 1}")
        merged_content += f"### {title}\n{content_text}\n\n"
        sources.add(title)

    return {
        "found": len(results) > 0,
        "content": merged_content,
        "confidence": min(best_score + 0.1, 1.0) if results else 0.0,
        "source": ", ".join(sources) if sources else "None",
        "results": results,
    }


async def _do_internet_search(q: str):
    try:
        report = await research_client.deep_research(q)
        return {
            "used": True,
            "content": report,
            "confidence": 0.85,
            "source": "Tavily / Firecrawl Web Search",
        }
    except Exception as e:
        logger.error(f"Internet search failed: {e}")
        return {
            "used": False,
            "content": f"Internet search failed: {e!s}",
            "confidence": 0.0,
            "source": "Error",
        }


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
    Advanced Two-Layer Hybrid Search System for INTERNAL DB and INTERNET SEARCH.
    """
    try:
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
        raw_args = {**filtered_args, **kwargs}
        validated_data = SearchContentSchema(**raw_args)
        q = validated_data.q
        level = validated_data.level
        subject = validated_data.subject
        branch = validated_data.branch
        set_name = validated_data.set_name
        year = validated_data.year
        type = validated_data.type
        limit = validated_data.limit
    except Exception as e:
        logger.error(f"Schema Validation Failed in search_content: {e}")
        raise e

    if not q:
        return []

    normalized_branch = _normalize_branch(branch) if branch else branch

    context_parts = []
    if subject:
        context_parts.append(f"Subject: {subject}")
    if normalized_branch:
        context_parts.append(f"Branch: {normalized_branch}")
    if year:
        context_parts.append(f"Year: {year}")
    if level:
        context_parts.append(f"Level: {level}")

    full_query = q
    if context_parts:
        full_query += f" ({', '.join(context_parts)})"

    # Smart Router Logic
    is_edu = is_educational_content(full_query, subject, normalized_branch, year)
    is_gen = is_general_knowledge(full_query)

    internal_used = False
    web_used = False
    hybrid_mode = False
    final_content = ""
    final_confidence = 0.0
    final_source = ""

    if is_edu:
        internal_res = await _do_internal_search(
            q, limit, subject, normalized_branch, set_name, year, type
        )
        if internal_res["found"] and internal_res["confidence"] >= 0.70:
            internal_used = True
            final_content = internal_res["content"]
            final_confidence = internal_res["confidence"]
            final_source = internal_res["source"]
        else:
            # Hybrid Merge (STEP 4 -> ESCALATE to Layer 2)
            hybrid_mode = True
            web_res = await _do_internet_search(full_query)

            internal_used = internal_res["found"]
            web_used = web_res["used"]

            final_content = ""
            if internal_used:
                final_content += f"### INTERNAL RESULTS\n{internal_res['content']}\n"
            if web_used:
                final_content += f"### WEB RESULTS\n{web_res['content']}"

            final_confidence = max(internal_res["confidence"], web_res["confidence"])
            final_source = (internal_res["source"] + " & " + web_res["source"]).strip(" &")

    elif is_gen:
        web_res = await _do_internet_search(full_query)
        web_used = web_res["used"]
        final_content = web_res["content"]
        final_confidence = web_res["confidence"]
        final_source = web_res["source"]

    else:
        # Parallel Search
        hybrid_mode = True
        internal_task = asyncio.create_task(
            _do_internal_search(q, limit, subject, normalized_branch, set_name, year, type)
        )
        web_task = asyncio.create_task(_do_internet_search(full_query))

        internal_res, web_res = await asyncio.gather(internal_task, web_task)

        internal_used = internal_res["found"]
        web_used = web_res["used"]

        final_content = ""
        if internal_used:
            final_content += f"### INTERNAL RESULTS\n{internal_res['content']}\n"
        if web_used:
            final_content += f"### WEB RESULTS\n{web_res['content']}"

        final_confidence = (internal_res["confidence"] * 0.65) + (web_res["confidence"] * 0.35)
        final_source = (internal_res["source"] + " & " + web_res["source"]).strip(" &")

    formatted_response = format_search_response(
        content=final_content,
        internal_used=internal_used,
        web_used=web_used,
        hybrid_mode=hybrid_mode,
        confidence=final_confidence,
        source=final_source,
    )

    return [
        {
            "id": "search_result",
            "title": f"Search Report: {q}",
            "content": formatted_response,
            "type": "report",
            "metadata": {
                "query": full_query,
                "confidence": final_confidence,
                "source": final_source,
            },
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

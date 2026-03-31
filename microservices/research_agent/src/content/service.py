from sqlalchemy import text

from microservices.research_agent.src.content.query_builder import ContentSearchQuery
from microservices.research_agent.src.content.repository import ContentRepository
from microservices.research_agent.src.content.utils import (
    normalize_branch,
    normalize_set_name,
    normalize_subject,
)
from microservices.research_agent.src.database import (
    async_session_factory as default_session_factory,
)
from microservices.research_agent.src.logging import get_logger

logger = get_logger("content-service")


class ContentService:
    """طبقة خدمة لإدارة المحتوى مع توحيد المدخلات وبناء الاستعلامات."""

    def __init__(self, session_factory=None):
        self.session_factory = session_factory or default_session_factory

    async def search_content(
        self,
        q: str | None = None,
        level: str | None = None,
        subject: str | None = None,
        branch: str | None = None,
        set_name: str | None = None,
        year: int | None = None,
        type: str | None = None,
        lang: str | None = None,
        content_ids: list[str] | None = None,
        preserve_content_id_order: bool = False,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """يبني استعلام بحث هجين مع فلاتر وصفية متوافقة مع الاختبارات."""

        norm_set = normalize_set_name(set_name)
        norm_branch = normalize_branch(branch)
        norm_subject = normalize_subject(subject)

        builder = ContentSearchQuery()
        builder.add_text_search(q)
        builder.add_id_filter(content_ids)
        builder.add_filter("i.level", level)
        builder.add_filter("i.subject", norm_subject)
        builder.add_filter("i.branch", norm_branch)
        builder.add_filter("i.set_name", norm_set)
        builder.add_filter("i.year", year)
        builder.add_filter("i.type", type)
        builder.add_filter("i.lang", lang)

        has_structured_filters = any(
            value is not None and value != ""
            for value in (level, norm_subject, norm_branch, norm_set, year, type, lang)
        )
        if preserve_content_id_order and content_ids:
            builder.set_order_by_vector_ids(content_ids)
        elif q and not has_structured_filters and not content_ids:
            builder.set_order_by_text_relevance()

        builder.set_limit(limit)

        query_str, params = builder.build()

        logger.info(f"Executing Search SQL: {query_str}")
        logger.info(f"Search Params: {params}")

        try:
            session_factory = self.session_factory()
        except ValueError as exc:
            logger.warning(f"Database unavailable for content search: {exc}")
            return []

        async with session_factory() as session:
            result = await session.execute(text(query_str), params)
            rows = result.fetchall()
            logger.info(f"Search returned {len(rows)} rows.")

        return [
            {
                "id": row[0],
                "title": row[1],
                "type": row[2],
                "level": row[3],
                "subject": row[4],
                "branch": row[5],
                "set": row[6],
                "year": row[7],
                "lang": row[8],
                "content": row[9],
            }
            for row in rows
        ]

    async def get_content_raw(
        self, content_id: str, *, include_solution: bool = True
    ) -> dict[str, str] | None:
        """
        جلب النص الخام (Markdown) لعنصر المحتوى مع التحكم في إرفاق الحل.
        """
        try:
            session_factory = self.session_factory()
        except ValueError as exc:
            logger.warning(f"Database unavailable for content detail: {exc}")
            return None

        async with session_factory() as session:
            repo = ContentRepository(session)
            detail = await repo.get_content_detail(content_id)

        if not detail:
            return None

        data = {"content": detail.content_md}
        if include_solution and detail.solution_md:
            data["solution"] = detail.solution_md

        return data

    async def get_curriculum_structure(self, level: str | None = None) -> dict[str, object]:
        try:
            session_factory = self.session_factory()
        except ValueError as exc:
            logger.warning(f"Database unavailable for curriculum structure: {exc}")
            return {}

        async with session_factory() as session:
            repo = ContentRepository(session)
            rows = await repo.get_tree_items(level)

        structure = {}
        for row in rows:
            # row is a result proxy, access by name
            # id, title, type, level, subject, branch, set_name, year
            subj = row.subject or "Uncategorized"
            lvl = row.level or "General"
            pack = row.set_name or "Misc"

            if subj not in structure:
                structure[subj] = {"type": "subject", "levels": {}}
            if lvl not in structure[subj]["levels"]:
                structure[subj]["levels"][lvl] = {"type": "level", "packs": {}}
            if pack not in structure[subj]["levels"][lvl]["packs"]:
                structure[subj]["levels"][lvl]["packs"][pack] = {"type": "pack", "items": []}

            structure[subj]["levels"][lvl]["packs"][pack]["items"].append(
                {
                    "id": row.id,
                    "title": row.title or "Untitled",
                    "type": row.type or "exercise",
                    "year": row.year,
                }
            )

        return structure


# Singleton Instance
content_service = ContentService()

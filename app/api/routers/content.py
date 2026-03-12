from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

COMPATIBILITY_FACADE_MODE = True
CANONICAL_EXECUTION_AUTHORITY = "research-agent-content-domain"

router = APIRouter(prefix="/v1/content", tags=["content"])


class ContentItemResponse(BaseModel):
    id: str
    type: str
    title: str | None = None
    level: str | None = None
    subject: str | None = None
    year: int | None = None
    lang: str | None = None


class ContentSearchResponse(BaseModel):
    items: list[ContentItemResponse]


@router.get("/search", response_model=ContentSearchResponse)
async def search_content(
    q: str | None = Query(None, description="Search query"),
    level: str | None = None,
    subject: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Search content items.
    """
    query_str = "SELECT id, type, title, level, subject, year, lang FROM content_items WHERE 1=1"
    params = {}

    if level:
        query_str += " AND level = :level"
        params["level"] = level

    if subject:
        query_str += " AND subject = :subject"
        params["subject"] = subject

    if q:
        # Simple LIKE search for now (works on both sqlite and postgres)
        query_str += " AND (title LIKE :q OR md_content LIKE :q)"
        params["q"] = f"%{q}%"

    query_str += " LIMIT 50"

    result = await db.execute(text(query_str), params)
    rows = result.fetchall()

    items = []
    for row in rows:
        items.append(
            ContentItemResponse(
                id=row[0],
                type=row[1],
                title=row[2],
                level=row[3],
                subject=row[4],
                year=row[5],
                lang=row[6],
            )
        )

    return ContentSearchResponse(items=items)


@router.get("/{id}")
async def get_content(id: str, db: AsyncSession = Depends(get_db)):
    """
    Get content metadata and raw content.
    """
    result = await db.execute(
        text(
            "SELECT id, type, title, level, subject, year, lang, md_content FROM content_items WHERE id = :id"
        ),
        {"id": id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Content not found")

    return {
        "id": row[0],
        "type": row[1],
        "title": row[2],
        "level": row[3],
        "subject": row[4],
        "year": row[5],
        "lang": row[6],
        "md_content": row[7],
    }


@router.get("/{id}/raw")
async def get_content_raw(id: str, db: AsyncSession = Depends(get_db)):
    """
    Get raw markdown content.
    """
    result = await db.execute(
        text("SELECT md_content FROM content_items WHERE id = :id"), {"id": id}
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Content not found")

    return {"content": row[0]}


@router.get("/{id}/solution")
async def get_content_solution(id: str, db: AsyncSession = Depends(get_db)):
    """
    Get official solution.
    """
    result = await db.execute(
        text(
            "SELECT solution_md, steps_json, final_answer FROM content_solutions WHERE content_id = :id"
        ),
        {"id": id},
    )
    row = result.fetchone()

    # If no solution found, return 404 or empty structure?
    # User said: "If solution_md is missing... say you don't have a verified solution"
    # The API should simply return 404 or nulls.

    if not row:
        raise HTTPException(status_code=404, detail="Solution not found")

    return {"solution_md": row[0], "steps_json": row[1], "final_answer": row[2]}

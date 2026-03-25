from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from microservices.conversation_service.database import get_conv_db_session

router = APIRouter(prefix="/api/v1/conversations")

class ImportConversationRequest(BaseModel):
    conversation_id: int
    user_id: int
    idempotency_key: str = Field(min_length=3)
    max_messages: int = Field(default=50, ge=1, le=200)
    conversation_metadata: dict[str, object]
    messages: list[dict[str, object]]

class ImportConversationResponse(BaseModel):
    status: str
    conversation_id: int
    messages_imported: int


async def _find_conversation_in_conv_db(session: AsyncSession, conversation_id: int) -> bool:
    res = await session.execute(
        text("SELECT 1 FROM conversation_import_audit WHERE conversation_id = :cid"),
        {"cid": conversation_id}
    )
    return res.scalar() is not None

async def _insert_conversation(session: AsyncSession, req: ImportConversationRequest) -> None:
    # Use ON CONFLICT DO NOTHING to ensure idempotency at the DB level for the conversation record.
    await session.execute(
        text("""
            INSERT INTO conversations
            (id, user_id, title, created_at, metadata)
            VALUES (:id, :uid, :title, :cat, :meta)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "id": req.conversation_id,
            "uid": req.user_id,
            "title": req.conversation_metadata.get("title", ""),
            "cat": req.conversation_metadata.get("created_at"),
            "meta": None
        }
    )

async def _insert_messages_batch(session: AsyncSession, req: ImportConversationRequest) -> None:
    messages_to_import = req.messages[:req.max_messages]
    if not messages_to_import:
        return

    for msg in messages_to_import:
        await session.execute(
            text("""
                INSERT INTO messages
                (conversation_id, role, content, created_at)
                VALUES (:cid, :role, :content, :cat)
                ON CONFLICT DO NOTHING
            """),
            {
                "cid": req.conversation_id,
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
                "cat": msg.get("created_at")
            }
        )

async def _record_import_audit(session: AsyncSession, req: ImportConversationRequest, messages_imported: int) -> None:
    await session.execute(
        text("""
            INSERT INTO conversation_import_audit
            (conversation_id, user_id, idempotency_key, messages_imported)
            VALUES (:cid, :uid, :ikey, :mi)
            ON CONFLICT (idempotency_key) DO NOTHING
        """),
        {
            "cid": req.conversation_id,
            "uid": req.user_id,
            "ikey": req.idempotency_key,
            "mi": messages_imported
        }
    )


@router.post("/import", response_model=ImportConversationResponse)
async def import_conversation(
    req: ImportConversationRequest,
    db: AsyncSession = Depends(get_conv_db_session)
):
    try:
        async with db.begin():
            res = await db.execute(
                text("SELECT 1 FROM conversation_import_audit WHERE idempotency_key = :ikey"),
                {"ikey": req.idempotency_key}
            )
            if res.scalar() is not None:
                return ImportConversationResponse(
                    status="already_exists",
                    conversation_id=req.conversation_id,
                    messages_imported=0
                )

            if not req.conversation_metadata and not req.messages:
                return ImportConversationResponse(
                    status="not_found_in_source",
                    conversation_id=req.conversation_id,
                    messages_imported=0
                )

            await _insert_conversation(db, req)
            messages_to_import = req.messages[:req.max_messages]
            await _insert_messages_batch(db, req)

            await _record_import_audit(db, req, len(messages_to_import))

            return ImportConversationResponse(
                status="imported",
                conversation_id=req.conversation_id,
                messages_imported=len(messages_to_import)
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

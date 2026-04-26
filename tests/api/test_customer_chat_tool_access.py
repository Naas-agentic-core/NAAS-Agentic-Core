from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.ai_gateway import get_ai_client
from app.core.database import get_db


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_tool_access_block_returns_fallback_event(
    test_app, db_session, register_and_login_test_user
) -> None:
    """يتحقق من إرجاع رسالة رفض آمنة عندما يحظر المنسق استخدام الأدوات."""

    def override_get_ai_client() -> object:
        return object()

    async def override_get_db() -> AsyncGenerator[object, None]:
        yield db_session

    async def _stream_fallback() -> AsyncGenerator[dict[str, object], None]:
        yield {
            "type": "assistant_fallback",
            "payload": {"content": "لا يمكنني تنفيذ هذا الطلب."},
        }

    test_app.dependency_overrides[get_ai_client] = override_get_ai_client
    test_app.dependency_overrides[get_db] = override_get_db

    try:
        from app.services.chat.intent_detector import ChatIntent
        from app.services.chat.tool_router import ToolAuthorizationDecision

        with patch(
            "app.api.routers.customer_chat.orchestrator_client.chat_with_agent",
            return_value=_stream_fallback(),
        ):
            with patch(
                "app.services.chat.tool_router.ToolRouter.authorize_intent",
                return_value=ToolAuthorizationDecision(
                    intent=ChatIntent.FILE_READ,
                    allowed=False,
                    reason_code="TOOL_NOT_ALLOWED",
                    refusal_message="عذرًا، لا يمكنني تنفيذ هذا الطلب.",
                ),
            ):
                token = await register_and_login_test_user(db_session, "tool-block@example.com")

            refusal_text = ""
            final_payload_type = ""
            with TestClient(test_app) as client:
                with client.websocket_connect(f"/api/chat/ws?token={token}") as websocket:
                    # Mock an intent that hits tool router
                    from app.services.chat.intent_detector import ChatIntent, IntentResult

                    with patch(
                        "app.services.chat.intent_detector.IntentDetector.detect",
                        return_value=IntentResult(
                            intent=ChatIntent.FILE_READ, confidence=0.99, params={}
                        ),
                    ):
                        websocket.send_json({"question": "read file secrets.txt"})
                        for _ in range(12):
                            try:
                                payload = websocket.receive_json()
                                final_payload_type = str(payload.get("type", ""))
                                if payload.get("type") == "assistant_fallback":
                                    refusal_text = str(
                                        payload.get("payload", {}).get("content", "")
                                    )
                                    break
                                if payload.get("type") == "error":
                                    refusal_text = str(
                                        payload.get("payload", {}).get("details", "")
                                    )
                                    break
                                if payload.get("type") == "delta":
                                    content = str(payload.get("payload", {}).get("content", ""))
                                    if "لا يمكنني" in content or "عذرًا" in content:
                                        refusal_text = content
                                        break
                            except Exception:
                                break

            assert (
                "لا يمكنني" in refusal_text
                or "error" in final_payload_type
                or "Policy violation" in refusal_text
                or "عذرًا" in refusal_text
            )
    finally:
        test_app.dependency_overrides.clear()

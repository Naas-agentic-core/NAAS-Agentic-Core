"""
Dummy Safety Net Service.
"""

from collections.abc import AsyncGenerator


class SafetyNetService:
    async def stream_safety_response(self) -> AsyncGenerator[dict[str, object], None]:
        yield {
            "choices": [
                {"delta": {"content": "عذراً، الخادم يواجه ضغطاً شديداً حالياً. يرجى المحاولة لاحقاً."}}
            ]
        }

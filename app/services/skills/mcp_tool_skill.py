"""
MCPToolSkill — جسر أدوات MCP (8 أدوات) كـ Skill رسمي وراء علم ميزة.

يُفعِّل `app/services/mcp/server.py:MCPServer` (8 أدوات تعمل لكن غير موصولة بمسار حي) كـ
**Skill** قابل للقياس والاختبار. يدعم عمليتين: `list` (مخطط الأدوات) و `call` (تنفيذ أداة).

> **مبدأ السلامة:** مُعطَّل افتراضياً (`ENABLE_MCP_TOOL_SKILL=False`). عند التعطيل أو الفشل →
> `None` فيستخدم المُستدعي مساره الحالي. `MCPServer._validate_access` يحرس الأدوات الحسّاسة —
> الرفض يُعاد كـ `{"error": "Access Denied"}` لا كاستثناء (لا يكسر المسار).

§0.5 contract: مسؤولية واحدة · عقد Pydantic · مقاييس Prometheus · اختبارات · استقلالية.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from pydantic import Field

from app.core.schemas import RobustBaseModel
from app.services.skills.base import BaseSkill

logger = logging.getLogger("cogniforge.skills.mcp_tool")

_FLAG = "ENABLE_MCP_TOOL_SKILL"

# ── مقاييس Prometheus (حارس ضد التسجيل المزدوج) ──
try:
    from prometheus_client import REGISTRY, Counter, Histogram

    if "cogniforge_skill_mcp_invocations" not in {m.name for m in REGISTRY.collect()}:
        _INVOCATIONS = Counter(
            "cogniforge_skill_mcp_invocations_total",
            "MCPToolSkill invocations",
            ["action", "status"],
        )
        _DURATION = Histogram(
            "cogniforge_skill_mcp_duration_seconds",
            "MCPToolSkill duration",
            ["action"],
        )
    else:  # pragma: no cover
        _INVOCATIONS = None
        _DURATION = None

    def _rec(action: str, status: str, dur: float) -> None:
        try:
            if _INVOCATIONS is not None:
                _INVOCATIONS.labels(action=action, status=status).inc()
                _DURATION.labels(action=action).observe(dur)
        except Exception:  # pragma: no cover
            pass

except Exception:  # pragma: no cover

    def _rec(action: str, status: str, dur: float) -> None:
        pass


class MCPToolInput(RobustBaseModel):
    """مدخلات جسر MCP."""

    action: Literal["list", "call"] = "list"
    tool_name: str | None = Field(default=None, max_length=128)
    arguments: dict[str, Any] | None = None
    #: سياق الأمان (يُمرَّر لـ MCPServer._validate_access للأدوات الحسّاسة)
    context: dict[str, Any] | None = None


class MCPToolOutput(RobustBaseModel):
    """مخرجات جسر MCP."""

    action: str
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_count: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None


class MCPToolSkill(BaseSkill[MCPToolInput, MCPToolOutput | None]):
    """Skill جسر أدوات MCP — list + call عبر MCPServer."""

    name = "mcp_tool"

    def run(self, payload: MCPToolInput):
        """Polymorphic entry point (BaseSkill) — delegates to :meth:`call` (async)."""
        return self.call(payload)

    @staticmethod
    def is_enabled() -> bool:
        # env var (override، 12-factor) أولاً ثم الإعدادات. الافتراضي False.
        import os

        raw = os.getenv(_FLAG)
        if raw is not None:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        try:
            from app.core.config import get_settings

            value = getattr(get_settings(), _FLAG, None)
            if isinstance(value, bool):
                return value
        except Exception:
            pass
        return False

    async def call(self, payload: MCPToolInput) -> MCPToolOutput | None:
        """ينفّذ list/call على خادم MCP. يُرجِع None عند التعطيل أو الفشل الكامل."""
        if not self.is_enabled():
            return None

        t0 = time.perf_counter()
        try:
            from app.services.mcp.server import get_mcp_server

            server = get_mcp_server()

            if payload.action == "list":
                tools = await server.get_tools_for_llm()
                _rec("list", "ok", time.perf_counter() - t0)
                return MCPToolOutput(action="list", tools=tools, tool_count=len(tools))

            # action == "call"
            if not payload.tool_name:
                _rec("call", "invalid", time.perf_counter() - t0)
                return MCPToolOutput(action="call", error="tool_name is required for action=call")

            result = await server.call_tool(
                payload.tool_name, payload.arguments or {}, payload.context
            )
            status = "denied" if isinstance(result, dict) and result.get("error") else "ok"
            _rec("call", status, time.perf_counter() - t0)
            return MCPToolOutput(action="call", result=result)

        except Exception as exc:
            _rec(payload.action, "error", time.perf_counter() - t0)
            logger.debug("mcp_tool skill non-fatal failure: %s", exc)
            return None


def get_mcp_tool_skill() -> MCPToolSkill:
    """يُعيد Singleton لمهارة جسر MCP (BaseSkill.instance)."""
    return MCPToolSkill.instance()

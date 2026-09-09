"""
RetrievalRerankSkill — استرجاع دلالي (LlamaIndex) + إعادة ترتيب (Reranker/CrossEncoder).

يُفعِّل قدرتين كانتا DORMANT (`app/drivers/llamaindex_driver.py` +
`app/drivers/reranker_driver.py`) كـ **Skill** رسمي وراء علم ميزة.

> **مبدأ السلامة:** مُعطَّل افتراضياً (`ENABLE_RETRIEVAL_RERANK_SKILL=False`). عند التعطيل أو
> أي فشل → يُرجِع `None` فيستخدم المُستدعي مساره الحالي (صفر تغيير سلوكي). الـ drivers نفسها
> تُعالج الفشل بـ try/except وتُرجِع `{"success": False, ...}` — لا ترفع أبداً.

§0.5 contract: مسؤولية واحدة · عقد Pydantic · مقاييس Prometheus · اختبارات · استقلالية.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import Field

from app.core.schemas import RobustBaseModel
from app.services.skills.base import BaseSkill

logger = logging.getLogger("cogniforge.skills.retrieval_rerank")

_FLAG = "ENABLE_RETRIEVAL_RERANK_SKILL"

# ── مقاييس Prometheus (حارس ضد التسجيل المزدوج) ──
try:
    from prometheus_client import REGISTRY, Counter, Histogram

    if "cogniforge_skill_retrieval_invocations" not in {m.name for m in REGISTRY.collect()}:
        _INVOCATIONS = Counter(
            "cogniforge_skill_retrieval_invocations_total",
            "RetrievalRerankSkill invocations",
            ["stage", "status"],
        )
        _DURATION = Histogram(
            "cogniforge_skill_retrieval_duration_seconds",
            "RetrievalRerankSkill duration",
            ["stage"],
        )
    else:  # pragma: no cover
        _INVOCATIONS = None
        _DURATION = None

    def _rec(stage: str, status: str, dur: float) -> None:
        try:
            if _INVOCATIONS is not None:
                _INVOCATIONS.labels(stage=stage, status=status).inc()
                _DURATION.labels(stage=stage).observe(dur)
        except Exception:  # pragma: no cover
            pass

except Exception:  # pragma: no cover

    def _rec(stage: str, status: str, dur: float) -> None:
        pass


class RetrievalRerankInput(RobustBaseModel):
    """مدخلات الاسترجاع + إعادة الترتيب."""

    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=50, description="عدد نتائج الاسترجاع الأولية")
    top_n: int = Field(default=5, ge=1, le=50, description="عدد النتائج بعد إعادة الترتيب")
    documents: list[str] | None = Field(
        default=None, description="وثائق صريحة لإعادة ترتيبها (يتخطّى الاسترجاع)"
    )
    filters: dict[str, Any] | None = Field(default=None, description="مرشّحات (سنة/مادة...)")


class RetrievalRerankOutput(RobustBaseModel):
    """مخرجات الاسترجاع + إعادة الترتيب."""

    query: str
    retrieved: list[dict[str, Any]] = Field(default_factory=list)
    reranked: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_count: int = 0
    reranked_count: int = 0
    source: str = "retrieval_rerank_skill"
    degraded: bool = False


class RetrievalRerankSkill(BaseSkill[RetrievalRerankInput, RetrievalRerankOutput]):
    """Skill استرجاع دلالي + إعادة ترتيب — مُغلَّف فوق LlamaIndex/Reranker drivers."""

    name = "retrieval_rerank"

    def run(self, payload: RetrievalRerankInput):
        """Polymorphic entry point (BaseSkill) — delegates to :meth:`retrieve` (async)."""
        return self.retrieve(payload)

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

    async def retrieve(self, payload: RetrievalRerankInput) -> RetrievalRerankOutput | None:
        """يُنفِّذ الاسترجاع ثم إعادة الترتيب. يُرجِع None عند التعطيل أو الفشل الكامل."""
        if not self.is_enabled():
            return None

        retrieved_docs: list[dict[str, Any]] = []
        degraded = False

        # ── المرحلة 1: استرجاع دلالي (LlamaIndex) — يُتخطّى إن وُفِّرت وثائق صريحة ──
        if payload.documents is None:
            t0 = time.perf_counter()
            try:
                from app.core.integration_kernel.ir import RetrievalQuery
                from app.drivers.llamaindex_driver import LlamaIndexDriver

                res = await LlamaIndexDriver().search(
                    RetrievalQuery(
                        query=payload.query, top_k=payload.top_k, filters=payload.filters
                    )
                )
                if res.get("success"):
                    raw = res.get("results") or []
                    retrieved_docs = [_as_doc(r) for r in raw]
                    _rec("retrieve", "ok", time.perf_counter() - t0)
                else:
                    degraded = True
                    _rec("retrieve", "fallback", time.perf_counter() - t0)
            except Exception as exc:
                degraded = True
                _rec("retrieve", "error", time.perf_counter() - t0)
                logger.debug("retrieval_rerank retrieve non-fatal failure: %s", exc)
        else:
            retrieved_docs = [{"text": d, "score": None} for d in payload.documents]

        doc_texts = [d.get("text", "") for d in retrieved_docs if d.get("text")]
        if not doc_texts:
            return RetrievalRerankOutput(
                query=payload.query,
                retrieved=retrieved_docs,
                retrieved_count=len(retrieved_docs),
                degraded=degraded,
            )

        # ── المرحلة 2: إعادة الترتيب (Reranker / CrossEncoder) ──
        reranked: list[dict[str, Any]] = []
        t1 = time.perf_counter()
        try:
            from app.core.integration_kernel.ir import ScoringSpec
            from app.drivers.reranker_driver import RerankerDriver

            res = await RerankerDriver().rank(
                ScoringSpec(query=payload.query, documents=doc_texts, top_n=payload.top_n)
            )
            if res.get("success"):
                reranked = [_as_doc(r) for r in (res.get("reranked_results") or [])]
                _rec("rerank", "ok", time.perf_counter() - t1)
            else:
                degraded = True
                _rec("rerank", "fallback", time.perf_counter() - t1)
        except Exception as exc:
            degraded = True
            _rec("rerank", "error", time.perf_counter() - t1)
            logger.debug("retrieval_rerank rerank non-fatal failure: %s", exc)

        # تدهور رشيق: لو فشل إعادة الترتيب، أعِد الاسترجاع بترتيبه الأصلي (أعلى top_n)
        if not reranked:
            reranked = retrieved_docs[: payload.top_n]

        return RetrievalRerankOutput(
            query=payload.query,
            retrieved=retrieved_docs,
            reranked=reranked,
            retrieved_count=len(retrieved_docs),
            reranked_count=len(reranked),
            degraded=degraded,
        )


def _as_doc(item: Any) -> dict[str, Any]:
    """يُطبِّع عنصر نتيجة (str | dict | كائن) إلى dict موحَّد."""
    if isinstance(item, dict):
        text = item.get("text") or item.get("content") or item.get("document") or ""
        return {"text": str(text), "score": item.get("score")}
    return {"text": str(item), "score": None}


def get_retrieval_rerank_skill() -> RetrievalRerankSkill:
    """يُعيد Singleton لمهارة الاسترجاع + إعادة الترتيب (BaseSkill.instance)."""
    return RetrievalRerankSkill.instance()

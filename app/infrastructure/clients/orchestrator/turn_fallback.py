"""D-170 Stage A3: سلسلة الـ fallback المحلية (file-count → retrieval → explanation
→ local_graph → general_chat) — تُستدعى فقط حين `REQUIRE_ORCHESTRATOR=0`
(D-112: العمود الفقري الإلزامي يمنع السقوط الصامت افتراضياً)."""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import AsyncGenerator

from app.infrastructure.clients.orchestrator.turn_context import TurnContext

# نفس اسم الـ logger القديم عمداً — استمرارية السجلات (نمط D-163/D-164).
logger = logging.getLogger("orchestrator-client")


class TurnFallbackMixin:
    """سلسلة الـ fallback المحلية المحروسة — منقولة حرفياً من ذيل chat_with_agent."""

    async def _stage_local_fallback(self, ctx: TurnContext) -> AsyncGenerator[dict | str, None]:
        """سلسلة الـ fallback المحلية المحروسة (D-047/D-048/ISS-053) — خلف REQUIRE_ORCHESTRATOR=0."""
        question = ctx.question
        history_messages = ctx.history_messages
        conversation_id = ctx.conversation_id
        obs = ctx.obs
        _root_ctx = ctx.root_ctx
        _t0 = ctx.t0
        _effective_question = ctx.effective_question
        _explanation_decision = ctx.explanation_decision
        # تسجيل الـ fallback المحلي كـ metric — يُظهر في Grafana أن الخدمة المصغرة غير متاحة
        with contextlib.suppress(Exception):
            obs.record_metric(
                "routing.target.total",
                1.0,
                labels={"target": "local_fallback"},
            )

        _fb_t0 = time.perf_counter()
        _fb_ctx = None
        with contextlib.suppress(Exception):
            _fb_ctx = obs.start_trace(
                "orchestrator.fallback.file_intelligence",
                parent_context=_root_ctx,
                tags={"fallback_step": "file_intelligence"},
            )
        local_file_count_response = await self._build_local_file_count_response(question)
        try:
            if _fb_ctx:
                obs.end_span(
                    _fb_ctx.span_id,
                    status="OK" if local_file_count_response else "SKIP",
                    metrics={"duration_ms": (time.perf_counter() - _fb_t0) * 1000},
                )
        except Exception as e:
            logger.debug(f"Telemetry logging error (silenced): {e}")
        if local_file_count_response:
            if _root_ctx:
                with contextlib.suppress(Exception):
                    obs.end_span(
                        _root_ctx.span_id,
                        status="OK",
                        metrics={
                            "duration_ms": (time.perf_counter() - _t0) * 1000,
                            "fallback_path": 1.0,
                        },
                    )
            yield self._normalize_stream_event(
                {
                    "type": "assistant_delta",
                    "payload": {"content": local_file_count_response},
                }
            )
            yield self._normalize_stream_event(
                {"type": "assistant_final", "payload": {"content": ""}}
            )
            ctx.turn_complete = True
            return

        # ── Exercise retrieval — STREAMING path (D-048) ──
        # يبث محتوى التمرين المُسترجَع كلمة بكلمة بدل dump واحد كبير.
        # ISS-051: المسار القديم كان يُرسل النص الكامل في assistant_delta
        # واحد → لا typing-effect. الآن نُقسّم على حدود الأسطر/الكلمات.
        _ret_t0 = time.perf_counter()
        _ret_ctx = None
        with contextlib.suppress(Exception):
            _ret_ctx = obs.start_trace(
                "orchestrator.fallback.exercise_retrieval.stream",
                parent_context=_root_ctx,
                tags={"fallback_step": "exercise_retrieval_stream"},
            )
        ret_streamed_any = False
        ret_streamed_chars = 0
        try:
            async for chunk in self._stream_local_retrieval_response(question, history_messages):
                if not chunk:
                    continue
                ret_streamed_any = True
                ret_streamed_chars += len(chunk)
                yield self._normalize_stream_event(
                    {"type": "assistant_delta", "payload": {"content": chunk}}
                )
        except Exception:
            logger.warning("local_retrieval_stream_yield_failed", exc_info=True)

        try:
            if _ret_ctx:
                obs.end_span(
                    _ret_ctx.span_id,
                    status="OK" if ret_streamed_any else "SKIP",
                    metrics={
                        "duration_ms": (time.perf_counter() - _ret_t0) * 1000,
                        "stream_chars": float(ret_streamed_chars),
                    },
                )
        except Exception as e:
            logger.debug(f"Telemetry logging error (silenced): {e}")

        if ret_streamed_any:
            if _root_ctx:
                with contextlib.suppress(Exception):
                    obs.end_span(
                        _root_ctx.span_id,
                        status="OK",
                        metrics={
                            "duration_ms": (time.perf_counter() - _t0) * 1000,
                            "fallback_path": 2.0,
                            "stream_chars": float(ret_streamed_chars),
                        },
                    )
            yield self._normalize_stream_event(
                {"type": "assistant_final", "payload": {"content": ""}}
            )
            ctx.turn_complete = True
            return

        # ── Exercise explanation with context — ISS-053 ──────────────────
        # يشرح تمرين بكالوريا محدد بالاعتماد على محتواه الكامل (نص + إجابة نموذجية).
        # يحل هلوسة LangGraph عند "اشرح تمرين الدوال العددية 2016".
        # يُدرَج قبل LangGraph لأنه أدق وأكثر موثوقية للتمارين المعروفة.
        _exp_t0 = time.perf_counter()
        _exp_ctx = None
        with contextlib.suppress(Exception):
            _exp_ctx = obs.start_trace(
                "orchestrator.fallback.exercise_explanation.stream",
                parent_context=_root_ctx,
                tags={"fallback_step": "exercise_explanation_stream"},
            )
        exp_streamed_any = False
        exp_streamed_chars = 0
        try:
            async for chunk in self._stream_exercise_explanation_response(
                question=question,
                conversation_id=conversation_id,
                history_messages=history_messages,
                # ISS-059 + D-103: القرار محسوب مسبقاً في بداية chat_with_agent —
                # لا إعادة كشف ولا file I/O مكرَّر في مسار الـ fallback.
                precomputed_decision=(
                    _explanation_decision
                    if (
                        _explanation_decision.recognized
                        and _explanation_decision.matched_entry is not None
                    )
                    else None
                ),
            ):
                if not chunk:
                    continue
                exp_streamed_any = True
                exp_streamed_chars += len(chunk)
                yield self._normalize_stream_event(
                    {"type": "assistant_delta", "payload": {"content": chunk}}
                )
        except Exception:
            logger.warning("exercise_explanation_stream_yield_failed", exc_info=True)

        try:
            if _exp_ctx:
                obs.end_span(
                    _exp_ctx.span_id,
                    status="OK" if exp_streamed_any else "SKIP",
                    metrics={
                        "duration_ms": (time.perf_counter() - _exp_t0) * 1000,
                        "stream_chars": float(exp_streamed_chars),
                    },
                )
        except Exception as e:
            logger.debug(f"Telemetry logging error (silenced): {e}")

        if exp_streamed_any:
            if _root_ctx:
                with contextlib.suppress(Exception):
                    obs.end_span(
                        _root_ctx.span_id,
                        status="OK",
                        metrics={
                            "duration_ms": (time.perf_counter() - _t0) * 1000,
                            "fallback_path": 2.5,
                            "stream_chars": float(exp_streamed_chars),
                        },
                    )
            yield self._normalize_stream_event(
                {"type": "assistant_final", "payload": {"content": ""}}
            )
            ctx.turn_complete = True
            return

        # ── LangGraph local engine — STREAMING path (D-047) ──
        # يبث الرد كلمة بكلمة عبر assistant_delta بدل dump واحد كبير.
        _lg_t0 = time.perf_counter()
        _lg_ctx = None
        with contextlib.suppress(Exception):
            _lg_ctx = obs.start_trace(
                "orchestrator.fallback.langgraph.stream",
                parent_context=_root_ctx,
                tags={
                    "fallback_step": "langgraph_stream",
                    "conversation_id": str(conversation_id),
                },
            )
        streamed_any = False
        streamed_chars = 0
        try:
            async for chunk in self._stream_local_graph_response(
                question=_effective_question,
                conversation_id=conversation_id,
                history_messages=history_messages,
            ):
                if not chunk:
                    continue
                streamed_any = True
                streamed_chars += len(chunk)
                yield self._normalize_stream_event(
                    {"type": "assistant_delta", "payload": {"content": chunk}}
                )
        except Exception:
            logger.warning("local_graph_stream_yield_failed", exc_info=True)

        try:
            if _lg_ctx:
                obs.end_span(
                    _lg_ctx.span_id,
                    status="OK" if streamed_any else "SKIP",
                    metrics={
                        "duration_ms": (time.perf_counter() - _lg_t0) * 1000,
                        "stream_chars": float(streamed_chars),
                    },
                )
        except Exception as e:
            logger.debug(f"Telemetry logging error (silenced): {e}")

        if streamed_any:
            if _root_ctx:
                with contextlib.suppress(Exception):
                    obs.end_span(
                        _root_ctx.span_id,
                        status="OK",
                        metrics={
                            "duration_ms": (time.perf_counter() - _t0) * 1000,
                            "fallback_path": 3.0,
                            "stream_chars": float(streamed_chars),
                        },
                    )
            yield self._normalize_stream_event(
                {"type": "assistant_final", "payload": {"content": ""}}
            )
            ctx.turn_complete = True
            return

        # Ultimate safety net: STREAMING raw LLM call (no graph, no state) — D-047
        is_file_intelligence = self._file_intelligence_decision(question)[0]
        is_exercise_retrieval = self._exercise_retrieval_decision(question, history_messages)
        if not is_file_intelligence and not is_exercise_retrieval:
            _gc_t0 = time.perf_counter()
            _gc_ctx = None
            with contextlib.suppress(Exception):
                _gc_ctx = obs.start_trace(
                    "orchestrator.fallback.general_chat.stream",
                    parent_context=_root_ctx,
                    tags={"fallback_step": "general_chat_stream"},
                )
            gc_streamed_any = False
            gc_streamed_chars = 0
            try:
                async for chunk in self._stream_local_general_chat_response(
                    _effective_question,
                    history_messages=history_messages,
                ):
                    if not chunk:
                        continue
                    gc_streamed_any = True
                    gc_streamed_chars += len(chunk)
                    yield self._normalize_stream_event(
                        {"type": "assistant_delta", "payload": {"content": chunk}}
                    )
            except Exception:
                logger.warning("local_general_chat_stream_yield_failed", exc_info=True)

            try:
                if _gc_ctx:
                    obs.end_span(
                        _gc_ctx.span_id,
                        status="OK" if gc_streamed_any else "SKIP",
                        metrics={
                            "duration_ms": (time.perf_counter() - _gc_t0) * 1000,
                            "stream_chars": float(gc_streamed_chars),
                        },
                    )
            except Exception as e:
                logger.debug(f"Telemetry logging error (silenced): {e}")

            if gc_streamed_any:
                if _root_ctx:
                    with contextlib.suppress(Exception):
                        obs.end_span(
                            _root_ctx.span_id,
                            status="OK",
                            metrics={
                                "duration_ms": (time.perf_counter() - _t0) * 1000,
                                "fallback_path": 4.0,
                                "stream_chars": float(gc_streamed_chars),
                            },
                        )
                yield self._normalize_stream_event(
                    {"type": "assistant_final", "payload": {"content": ""}}
                )
                ctx.turn_complete = True
                return

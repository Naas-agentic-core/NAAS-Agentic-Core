"""Chat-turn orchestration mixin (D-166 Slice 6 — extracted verbatim from the God-file).

Single responsibility: `chat_with_agent` — the full streaming chat turn: the preempt chain
(greeting → question-only slice → socratic interception → indexed retrieval → cognitive
turn → calculated UI → explanation-with-context → definitional/conceptual layers), the
orchestrator-microservice HTTP candidates (D-112 mandatory backbone), and the guarded
local fallback chain — plus the `EXPLANATION_VIA_ORCHESTRATOR` rollback lever (D-103).

This was the last God-method (~1,840 lines) left in `orchestrator_client.py`; the client
is now a thin transport shell (decisions + JWT + missions). Mixed into
`OrchestratorClient`; every `self._x` resolves through the MRO — behaviour is
byte-identical to the pre-extraction God-file (D-164 pattern: verbatim move, zero rewrite).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncGenerator

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.infrastructure.clients.orchestrator.turn_context import TurnContext
from app.infrastructure.clients.orchestrator.turn_fallback import TurnFallbackMixin
from app.infrastructure.clients.orchestrator.turn_preempts_cognitive import (
    TurnPreemptsCognitiveMixin,
)
from app.infrastructure.clients.orchestrator.turn_preempts_concept import (
    TurnPreemptsConceptMixin,
)
from app.infrastructure.clients.orchestrator.turn_preempts_delivery import (
    TurnPreemptsDeliveryMixin,
)
from app.infrastructure.clients.orchestrator.turn_preempts_deterministic import (
    TurnPreemptsDeterministicMixin,
)
from app.infrastructure.clients.routing_policy import ChatRoutingPolicy

# نفس اسم الـ logger القديم عمداً — استمرارية السجلات وصفر تغيير رصدي (نمط D-163/D-164).
logger = logging.getLogger("orchestrator-client")


class ChatTurnMixin(
    TurnPreemptsDeterministicMixin,
    TurnPreemptsConceptMixin,
    TurnPreemptsCognitiveMixin,
    TurnPreemptsDeliveryMixin,
    TurnFallbackMixin,
):
    """The full streaming chat turn — preempts, orchestrator HTTP, guarded fallbacks."""

    @staticmethod
    def _explanation_via_orchestrator_enabled() -> bool:
        """D-103: هل يُمرَّر شرح التمارين عبر orchestrator (الرسم الـ13-node)؟

        رافعة رجوع فورية بلا deploy (نمط D-025 / routing_policy):
        ``EXPLANATION_VIA_ORCHESTRATOR=0`` يعيد السلوك المحلي القديم.
        """
        raw = os.getenv("EXPLANATION_VIA_ORCHESTRATOR", "1").strip().lower()
        return raw not in ("0", "false", "no")

    # ISS-131 (D-169): مفاتيح داخلية للمونوليث لا تركب سلك HTTP نحو الـ orchestrator.
    # `policy_decision` = dataclass قرار المحرّك التربوي (غير قابل لـ JSON — كان يُفشل
    # تسلسل الجسم فيفشل كل مرشّحي الـ orchestrator ⇒ ORCHESTRATOR_REQUIRED للأسئلة
    # العامة). `tutor_state` = ذاكرة التدريس الدائمة (D-142) — ملكية المونوليث حصراً؛
    # الـ orchestrator يستهلك `support_level`/`exercise_content` المستخرجَين منفصلَين.
    _INTERNAL_CONTEXT_KEYS: frozenset[str] = frozenset({"policy_decision", "tutor_state"})

    @classmethod
    def _sanitize_wire_context(cls, context: dict[str, object] | None) -> dict[str, object]:
        """نسخة الـ context الصالحة للسلك — بلا مفاتيح داخلية غير قابلة للتسلسل."""
        if not isinstance(context, dict):
            return {}
        return {k: v for k, v in context.items() if k not in cls._INTERNAL_CONTEXT_KEYS}

    async def chat_with_agent(
        self,
        question: str,
        user_id: int,
        conversation_id: int | None = None,
        history_messages: list[dict[str, str]] | None = None,
        context: dict[str, object] | None = None,
    ) -> AsyncGenerator[dict | str, None]:
        """
        Chat with the Orchestrator Agent (Microservice).
        Expects NDJSON stream from the service.
        Yields either structured event dictionaries or fallback strings.
        """

        from app.telemetry.unified_observability import get_unified_observability

        obs = get_unified_observability()
        _t0 = time.perf_counter()
        _root_ctx = None
        with contextlib.suppress(Exception):
            _root_ctx = obs.start_trace(
                "orchestrator.chat_with_agent",
                tags={
                    "user_id": str(user_id),
                    "conversation_id": str(conversation_id),
                    "question_len": len(question),
                },
            )

        # D-170: سياق الدور + سلسلة المراحل — **الترتيب هو العقد** (ISS-110/
        # D-101/D-124/D-155): كل مرحلة تبثّ أحداثها وتضبط ctx.turn_complete عند
        # اكتمال الدور فيتوقف المُنسِّق فوراً. الكتل نفسها منقولة حرفياً إلى
        # mixins المراحل (انظر TUTOR_SOURCE_FILES) — صفر تغيير دلالي.
        ctx = TurnContext(
            question=question,
            user_id=user_id,
            conversation_id=conversation_id,
            history_messages=history_messages,
            context=context,
            obs=obs,
            t0=_t0,
            root_ctx=_root_ctx,
        )
        for _stage in (
            self._stage_policy_gate,
            self._stage_greeting,
            self._stage_question_only,
            self._stage_computational,
            self._stage_escalation_matrix,
            self._stage_definitional,
            self._stage_concept_example,
            self._stage_socratic_evaluation,
            self._stage_indexed_retrieval,
            self._stage_escape_hatch,
            self._stage_calculated_ui,
            self._stage_explanation_context,
        ):
            async for _ev in _stage(ctx):
                yield _ev
            if ctx.turn_complete:
                return

        _is_mode_b = ctx.is_mode_b
        _exercise_injection = ctx.exercise_injection

        # V38.0 — Deep Pedagogy Mode (MODE_B): inject Socratic instruction.
        # Rules (D-067): prompt < 1000 chars, no box-drawing chars, no LaTeX in prompt.
        # The instruction is prepended to the question so the LLM receives it as
        # user intent — not as a system override that triggers reasoning mode.
        _deep_pedagogy_instruction = (
            "[وضع الشرح العميق] "
            "الطالب يعبّر عن حيرة. ابدأ بالمعنى والصورة الذهنية قبل أي صيغة. "
            "استخدم أسلوباً سقراطياً دافئاً. "
            "لا تبدأ بـ LaTeX أو رموز رياضية. "
            "اشرح لماذا يحدث هذا قبل كيف يُحسب."
        )
        _effective_question = (
            _deep_pedagogy_instruction + "\n\n" + question if _is_mode_b else question
        )

        # D-117 (فصل الطبقات: الطالب يرى التعليم لا هندسة التعليم): التوجيه التربوي
        # (D-104) لم يَعُد يُسبَق للسؤال. كان النموذج المجاني يُردّده حرفياً
        # («[توجيه تربوي] ... مستوى الدعم: ...») فيرى الطالب «هندسة التعليم» لا
        # التعليم. عمق التدريس يصل الآن عبر `support_level` (مُمرَّر في context →
        # يستهلكه SynthesizerNode في الرسم). التوجيه يبقى في context للقياس فقط
        # (يصل ضمن `**(context or {})` في الـ payload) — لا يُسبَق للسؤال أبداً.

        # D-114: support_level يحكم إعفاء الحجب (sanitize_final_text). الافتراض
        # الآمن = 5 (محجوب كلياً) عند الغياب/الخطأ — لا 1 (fail-closed).
        try:
            _support_level = int((context or {}).get("support_level") or 5)
        except (TypeError, ValueError):
            _support_level = 5
        if _support_level < 1 or _support_level > 5:
            _support_level = 5

        # ISS-131 (D-169): معرّف محادثة الإدمن يعيش في جدول `admin_conversations`
        # (فضاء أسماء منفصل — ISS-019) بينما `_ensure_conversation` في الـ orchestrator
        # يتحقق من الملكية ضد فضاء محادثات العميل ⇒ تمريره يُرجِع 403 لكل دور إدمن.
        # الحل: لا يُمرَّر عبر الحدود — الـ orchestrator يشتق محادثته من session/thread،
        # والمونوليث يبقى المالك الوحيد لحفظ رسائل الإدمن (D-006 fail-safe write).
        _wire_conversation_id = (
            None
            if isinstance(context, dict) and context.get("chat_scope") == "admin"
            else conversation_id
        )
        payload = {
            "question": _effective_question,
            "user_id": user_id,
            "conversation_id": _wire_conversation_id,
            "history_messages": history_messages or [],
            "context": {
                **self._sanitize_wire_context(context),
                "routing_mode": "MODE_B" if _is_mode_b else "MODE_A",
                # D-103: محتوى التمرين المحقون (إن وُجد) — الرسم يستهلكه بدل retriever-ه
                **_exercise_injection,
            },
        }

        routing_policy = ChatRoutingPolicy.from_environment(self.base_url)
        candidate_urls = routing_policy.candidate_urls()
        client = await self._get_client()
        request_id = str(uuid.uuid4())
        connection_errors: list[str] = []
        contract_version = routing_policy.contract_version
        fallback_enabled = routing_policy.fallback_enabled

        # تسجيل وضع التوجيه كـ gauge قابل للقياس في Grafana :3001
        # cogniforge_routing_mode_state_graph: 1 = StateGraph, 0 = Agent
        # cogniforge_routing_target_total{target=...}: عداد تراكمي لكل هدف
        try:
            _obs_routing = obs
            _obs_routing.record_metric(
                "routing.mode.state_graph",
                1.0 if routing_policy.targets_state_graph else 0.0,
                labels={"endpoint_mode": routing_policy.endpoint_mode},
            )
            _obs_routing.record_metric(
                "routing.target.total",
                1.0,
                labels={"target": routing_policy.endpoint_mode},
            )
        except Exception as exc:
            logger.warning(
                "chat_contract_routing_metrics_failed",
                extra={
                    "metric": "routing.target.total",
                    "target": routing_policy.endpoint_mode,
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )

        logger.info(
            "chat_contract_route_start",
            extra={
                "request_id": request_id,
                "contract_version": contract_version,
                "candidate_count": len(candidate_urls),
                "fallback_enabled": fallback_enabled,
                "endpoint_mode": routing_policy.endpoint_mode,
                "targets_state_graph": routing_policy.targets_state_graph,
            },
        )

        # توليد JWT داخلي لمصادقة الـ monolith مع orchestrator-service
        # يُجدَّد مع كل طلب لضمان عدم انتهاء الصلاحية.
        # ISS-131 (D-169): القناة الإدارية تحمل claim الإدمن (درس D-162/§6.78) —
        # بدونه ValidateAccessNode يرفض أدوات الإدمن بـ ADMIN_ACCESS_DENIED.
        try:
            service_token = self._build_service_jwt(
                user_id,
                is_admin=isinstance(context, dict) and context.get("chat_scope") == "admin",
            )
            auth_headers = {
                "Authorization": f"Bearer {service_token}",
                "X-Correlation-ID": request_id,
                "X-Service-Source": "cogniforge-monolith",
            }
        except Exception as jwt_err:
            logger.warning("service_jwt_generation_failed: %s", jwt_err)
            auth_headers = {"X-Correlation-ID": request_id}

        for candidate_url in candidate_urls:
            try:
                logger.info(
                    "chat_routing_attempt",
                    extra={"candidate_url": candidate_url, "request_id": request_id},
                )
                response: httpx.Response | None = None

                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(1),
                    wait=wait_exponential(multiplier=1, min=1, max=4),
                    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
                    reraise=True,
                ):
                    with attempt:
                        request = client.build_request(
                            "POST", candidate_url, json=payload, headers=auth_headers
                        )
                        response = await client.send(request, stream=True)

                if response is None:
                    continue

                try:
                    response.raise_for_status()
                    # D-103: حارس البثّ الفارغ — orchestrator أجاب 200 لكن لم يبثّ
                    # أي محتوى مرئي ولا إطاراً نهائياً ⇒ نعامله كفشل ونُكمل للمرشح
                    # التالي / الـ fallback المحلي بدل إنهاء الدور فارغاً.
                    _orch_visible = False
                    # ISS-114 (D-106): الثغرة الكبرى — بثّ orchestrator HTTP كان
                    # يصل للطالب بلا حارس (غارباج لاتيني + HTML). نلفّه بمرشّح
                    # نزاهة المحتوى على كامل التيار. fail-open: None = سلوك اليوم.
                    _integrity = None
                    try:
                        from app.services.skills.content_integrity_skill import (
                            StreamIntegrityFilter,
                            sanitize_final_text,
                        )

                        _integrity = StreamIntegrityFilter()
                    except Exception as e:  # pragma: no cover - fail-open على مستوى التوصيل
                        logger.debug(f"StreamIntegrityFilter initialization failed (silenced): {e}")
                        _integrity = None
                        sanitize_final_text = None  # type: ignore[assignment]
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            parsed_line = json.loads(line)
                            normalized = self._normalize_stream_event(parsed_line)
                            _ntype = (
                                normalized.get("type") if isinstance(normalized, dict) else None
                            )
                            if _ntype == "assistant_delta":
                                _ncontent = (normalized.get("payload") or {}).get("content")
                                if isinstance(_ncontent, str) and _ncontent:
                                    # عقد empty_stream (D-103 rule 4): يُحسَب من
                                    # المحتوى الخام قبل الفلترة.
                                    _orch_visible = True
                                    if _integrity is not None:
                                        cleaned = _integrity.feed(_ncontent)
                                        if not cleaned:
                                            continue  # المرشّح حجز/حذف هذه القطعة
                                        normalized["payload"]["content"] = cleaned
                            elif _ntype == "assistant_final":
                                _orch_visible = True
                                if sanitize_final_text is not None:
                                    _fc = (normalized.get("payload") or {}).get("content")
                                    if isinstance(_fc, str) and _fc:
                                        # D-114: support_level==1 يُعفي كتلة المثال
                                        # المحلول الملفوفة بالفواصل من الحجب.
                                        normalized["payload"]["content"] = sanitize_final_text(
                                            _fc, _support_level
                                        )
                            elif _ntype in ("assistant_error", "error", "complete"):
                                _orch_visible = True
                            yield normalized
                        except json.JSONDecodeError:
                            recovered = self._recover_structured_event(line)
                            if recovered is not None:
                                _orch_visible = True
                                yield self._normalize_stream_event(recovered)
                            else:
                                logger.warning(f"Received non-JSON line from agent: {line[:50]}...")
                                _orch_visible = True
                                yield self._normalize_stream_event(line)
                    # ISS-114: إفراغ ذيل المرشّح المحجوز (صفر فقدان bytes).
                    if _integrity is not None:
                        _tail = _integrity.flush()
                        if _tail:
                            yield {
                                "type": "assistant_delta",
                                "payload": {"content": _tail},
                            }
                    if _orch_visible:
                        return
                    connection_errors.append(f"{candidate_url} => empty_stream")
                    logger.warning(
                        "chat_routing_empty_stream",
                        extra={
                            "request_id": request_id,
                            "candidate_url": candidate_url,
                        },
                    )
                finally:
                    await response.aclose()

            except Exception as e:
                connection_errors.append(f"{candidate_url} => {e}")
                logger.error(
                    "chat_routing_failed",
                    exc_info=True,
                    extra={"request_id": request_id, "candidate_url": candidate_url},
                )

        diagnostic = " | ".join(connection_errors) if connection_errors else "No endpoint attempted"
        logger.error(
            "Failed to chat with agent across all endpoints",
            extra={"diagnostic": diagnostic},
        )

        # ─────────────────────────────────────────────────────────────────────
        # D-112 (2026-06-13): العمود الفقري الإلزامي — الخدمات المصغرة + الرسم
        # الـ13-node هي القلب الوحيد. عند تعذّرها لا نسقط بصمت إلى local_graph
        # الضعيف؛ بل نُصدِر خطأً صريحاً («runtime truth over synthetic certainty»).
        # علم REQUIRE_ORCHESTRATOR=1 افتراضي مُفعَّل؛ =0 يُعيد الـ fallback القديم
        # (rollback بلا deploy — نمط D-025).
        # ─────────────────────────────────────────────────────────────────────
        _require_orch = os.environ.get("REQUIRE_ORCHESTRATOR", "1").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if _require_orch:
            logger.error(
                "orchestrator_required_hard_fail",
                extra={"request_id": request_id, "diagnostic": diagnostic},
            )
            with contextlib.suppress(Exception):
                obs.record_metric(
                    "routing.target.total",
                    1.0,
                    labels={"target": "orchestrator_required_error"},
                )
            if _root_ctx:
                with contextlib.suppress(Exception):
                    obs.end_span(
                        _root_ctx.span_id,
                        status="ERROR",
                        metrics={
                            "duration_ms": (time.perf_counter() - _t0) * 1000,
                            "hard_fail": 1.0,
                        },
                    )
            yield {
                "type": "error",
                "payload": {
                    "code": "ORCHESTRATOR_REQUIRED",
                    "message": (
                        "النظام يتطلب الخدمات الذكية المتقدمة وهي غير متاحة حالياً. "
                        "يرجى المحاولة بعد قليل."
                    ),
                },
            }
            return

        if fallback_enabled:
            ctx.effective_question = _effective_question
            async for _ev in self._stage_local_fallback(ctx):
                yield _ev
            if ctx.turn_complete:
                return

        # All paths exhausted — record error span and yield error event
        if _root_ctx:
            with contextlib.suppress(Exception):
                obs.end_span(
                    _root_ctx.span_id,
                    status="ERROR",
                    error_message="all_fallback_paths_exhausted",
                    metrics={"duration_ms": (time.perf_counter() - _t0) * 1000},
                )
        try:
            yield self._normalize_stream_event(self._sanitize_error_for_user(request_id=request_id))
            yield self._normalize_stream_event(
                {"type": "assistant_final", "payload": {"content": ""}}
            )
        except Exception as e:
            logger.error(f"Failed to chat with agent: {e}", exc_info=True)
            yield self._normalize_stream_event(self._sanitize_error_for_user(request_id=request_id))
            yield self._normalize_stream_event(
                {"type": "assistant_final", "payload": {"content": ""}}
            )

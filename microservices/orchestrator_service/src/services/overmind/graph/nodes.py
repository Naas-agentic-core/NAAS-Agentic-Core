"""Graph node classes + DSPy signatures — sliced verbatim from graph/main.py (D-173 Stage 2c).

نمط D-164/D-168: كل شريحة تُضاف لـ GRAPH_SOURCE_FILES؛ main.py يعيد التصدير
(noqa F401) فيبقى monkeypatch على `graph.main.<name>` والاستيراد الخارجي فعّالاً.
"""

import asyncio
import json
import logging
import os
import re

from .dspy_compat import dspy
from .state import (
    ADMIN_PATTERNS,
    ARABIC_PRONOUN_SUFFIXES,
    CHAT_INTENT_TRIGGERS,
    AgentState,
    _contains_anaphora_indicator,
    _looks_elliptical_followup,
    _resolve_query_from_history,
    _tokenize_query,
    build_conversation_context,
    emergency_intent_guard,
    format_conversation_history,
    get_message_content,
    get_message_role,
)

logger = logging.getLogger(__name__)


def _configure_dspy() -> None:
    """يضبط نموذج DSPy عالميًا في مرحلة الإقلاع باستخدام مفاتيح البيئة المتاحة."""
    if dspy.settings.lm is not None:
        return

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        import logging

        logging.getLogger("graph").warning(
            "CRITICAL: DSPy LM configuration skipped because OPENROUTER_API_KEY is missing."
        )
        return

    try:
        # ISS-068: nemotron-reasoning — أسرع نموذج مجاني مع reasoning tokens
        dspy_model = os.getenv(
            "OPENROUTER_DSPY_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free"
        ).strip()
        if not dspy_model.startswith("openai/"):
            dspy_model = f"openai/{dspy_model}"
        # DEADLOCK FIX: bound the structured-output call. Without an explicit
        # timeout (and with DSPy's default num_retries=8) a stalled free-tier
        # OpenRouter connection blocks SupervisorNode's worker thread forever,
        # hanging the graph at its entry node. A bounded call raises instead,
        # letting the deterministic heuristic fallback engage.
        lm = dspy.LM(
            model=dspy_model,
            api_base="https://openrouter.ai/api/v1",
            api_key=openrouter_key,
            timeout=25,
            num_retries=0,
        )
        dspy.settings.configure(lm=lm)
    except Exception as exc:
        import logging

        logging.getLogger("graph").warning(
            "CRITICAL: DSPy LM configuration failed; proceeding without LM. reason=%s", exc
        )


class IntentClassifier(dspy.Signature):
    """Classify if conversation needs admin system metrics, general chat/greetings, general knowledge, or educational search.
    educational: ONLY BAC exercises, school curriculum, exams.
    general_knowledge: Includes ALL factual questions including follow-ups that depend on history (e.g., pronouns like 'عاصمتها').
    admin: system metrics, service counts, operational information.
    chat: Only greetings and small talk. NEVER factual questions.
    Classify by DOMAIN, not by whether it is a follow-up.
    """

    history: str = dspy.InputField(
        desc="Previous conversation context to resolve pronouns and context"
    )
    question: str = dspy.InputField(
        desc="If the question contains pronouns or implicit entities, you MUST resolve them using history BEFORE classification."
    )
    resolved_question: str = dspy.OutputField(
        desc="The question rewritten with pronouns resolved using history"
    )
    intent: str = dspy.OutputField(desc="One of: educational, general_knowledge, admin, chat")
    confidence: float = dspy.OutputField()


class SupervisorNode:
    def __init__(self):
        self.dspy_classifier = dspy.ChainOfThought(IntentClassifier)

    async def __call__(self, state: AgentState) -> dict:
        """يوجّه النية بشكل غير حاجب للحلقة الحدثية مع أولوية للحراس الحتمية."""
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()

        # State Safety: Prevent query overwrite without backup
        if "original_query" not in state:
            # But wait, we can only update the state by returning a dict.
            # Mutating `state` directly doesn't persist the change unless it is returned.
            pass

        query = str(state.get("query", "")).strip()
        logger.debug("SupervisorNode query=%.80s", query)
        messages = state.get("messages", [])

        # Protect original query as SSOT backup BEFORE resolution
        updates = {}
        if "original_query" not in state:
            updates["original_query"] = query

        # D-103: محتوى تمرين محقون من الـ monolith ⇒ المسار تعليمي بالبناء —
        # الـ monolith حقنه فقط بعد detect_explanation_with_context. تصنيف حتمي
        # فوري (لا DSPy) يمنع misroute إلى chat/general يُضيع المحتوى المحقون.
        if str(state.get("exercise_content") or "").strip():
            updates["intent"] = "educational"
            updates["query"] = query
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return updates

        formatted_history = format_conversation_history(messages)
        resolved_q = _resolve_query_from_history(query=query, messages=messages)

        # Only adopt resolved query if it successfully extracted something meaningful
        if resolved_q and resolved_q != query:
            logger.debug("SupervisorNode resolved_query=%.80s", resolved_q)
            query = resolved_q
            updates["query"] = query

        if emergency_intent_guard(query):
            updates["intent"] = "admin"
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return updates

        query_normalized = query.strip().lower()
        if any(trigger in query_normalized for trigger in CHAT_INTENT_TRIGGERS):
            updates["intent"] = "chat"
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return updates

        for pattern in ADMIN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "admin", "query": query}

        try:
            # DEADLOCK FIX: separate routing from I/O — bound the structured-output
            # classification so a stalled LLM cannot freeze the entry node. On
            # timeout, asyncio.TimeoutError is caught below and routing falls
            # through to the deterministic free-response heuristic.
            result = await asyncio.wait_for(
                asyncio.to_thread(self.dspy_classifier, history=formatted_history, question=query),
                timeout=30.0,
            )
            try:
                conf = float(result.confidence)
            except (ValueError, TypeError):
                conf = 0.0

            if hasattr(result, "resolved_question") and result.resolved_question:
                resolved_q = result.resolved_question

            pred_intent = getattr(result, "intent", "").lower().strip()

            if pred_intent == "admin" and conf > 0.75:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                updates = {"intent": "admin", "query": resolved_q}
                if "original_query" not in state:
                    updates["original_query"] = state.get("query", "")
                return updates
            if pred_intent == "general_knowledge" and conf > 0.60:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                updates = {"intent": "general_knowledge", "query": resolved_q}
                if "original_query" not in state:
                    updates["original_query"] = state.get("query", "")
                return updates
            if pred_intent == "chat" and conf > 0.65:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                updates = {"intent": "chat", "query": resolved_q}
                if "original_query" not in state:
                    updates["original_query"] = state.get("query", "")
                return updates
            if pred_intent == "educational" and conf > 0.55:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                updates = {"intent": "educational", "query": resolved_q}
                if "original_query" not in state:
                    updates["original_query"] = state.get("query", "")
                return updates

        except Exception:
            pass

        if (
            len(query_normalized.split()) <= 3
            and "?" not in query_normalized
            and "؟" not in query
            and not _looks_elliptical_followup(query, formatted_history)
        ):
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            updates = {"intent": "chat", "query": query}
            if "original_query" not in state:
                updates["original_query"] = state.get("query", "")
            return updates

        educational_triggers = {
            "تمرين",
            "تمارين",
            "احتمالات",
            "دوال",
            "متتاليات",
            "بكالوريا",
            "bac",
            "احسب",
            "أحسب",
            "استنتج",
            "برهن",
            "بيّن",
            "بين",
            "معادلة",
            "مسألة",
            "دالة",
            "probability",
            "sequence",
            "function",
            "integral",
            "derivative",
        }
        if any(trigger in query_normalized for trigger in educational_triggers):
            intent = "educational"
        else:
            intent = "general_knowledge"

        emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
        updates = {"intent": intent, "query": query}
        if "original_query" not in state:
            updates["original_query"] = state.get("query", "")
        return updates


class ChatFallbackSignature(dspy.Signature):
    """صياغة رد محادثي طبيعي ومدروس للمحادثات العامة خارج مسارات البحث."""

    history: str = dspy.InputField(
        desc="Previous conversation context to resolve pronouns and context"
    )
    question: str = dspy.InputField()
    response: str = dspy.OutputField(desc="رد عربي طبيعي ومفيد للمستخدم")


class ChatFallbackNode:
    def __init__(self) -> None:
        self.generator = dspy.Predict(ChatFallbackSignature)

    @staticmethod
    def _get_writer():
        """D-048: stream_writer إذا توفر (وضع streaming)، None في وضع batch."""
        try:
            from langgraph.config import get_stream_writer

            return get_stream_writer()
        except Exception:
            return None

    async def __call__(self, state: AgentState) -> dict:
        import time

        from microservices.orchestrator_service.src.services.llm.client import (
            get_ai_client as get_llm_client,
        )
        from microservices.orchestrator_service.src.services.overmind.latex_normalizer import (
            LatexStreamNormalizer,
            normalize_latex,
        )
        from microservices.orchestrator_service.src.services.overmind.response_sanitizer import (
            get_greeting_fastpath_response,
            sanitize_chunk,
            sanitize_response,
        )

        from .telemetry import emit_telemetry

        start_time = time.time()
        messages = state.get("messages", [])

        query = state.get("query")
        if not query and messages:
            query = messages[-1].content
        query = str(query or "").strip()

        # ─── ISS-076 D-064: Greeting fast-path — تجنَّب LLM للتحيات الشائعة ────
        # السبب: نماذج OpenRouter المجانية تُولِّد etymology طويلة بكلمات أجنبية
        # عند سؤال "السلام عليكم" — فاستخدم رد deterministic مباشر.
        fastpath_response = get_greeting_fastpath_response(query)
        if fastpath_response:
            writer = self._get_writer()
            if writer is not None:
                # ابث الرد المُعَدَّ مسبقاً (للحفاظ على نفس واجهة الـ streaming)
                writer(
                    {
                        "chunk_type": "assistant_delta",
                        "content": fastpath_response,
                        "node": "chat_fallback_fastpath",
                    }
                )
            emit_telemetry(node_name="ChatFallbackNode", start_time=start_time, state=state)
            from langchain_core.messages import AIMessage

            return {
                "final_response": fastpath_response,
                "messages": [AIMessage(content=fastpath_response)],
            }
        # ─────────────────────────────────────────────────────────────────────

        history = format_conversation_history(messages)

        if not history.strip():
            logger.debug("ChatFallbackNode: empty history for query=%.60s", query)

        system_content = (
            "أجب بدقة اعتماداً على سياق المحادثة. لا تتجاهل السياق أبداً.\n"
            "اكتب بالعربية الفصحى فقط — لا تخلط مع الإنجليزية أو الروسية أو الإسبانية.\n"
            'اكتب ردك مباشرة — لا تكتب تفكيراً صوتياً ("Let me think", "Okay, the user").'
        )
        user_content = f"السياق:\n{history}\n\nالسؤال:\n{query}"

        fallback_response = (
            "وعليكم السلام! أنا هنا للمساعدة. أخبرني بما تحتاجه وسأتابع معك خطوة بخطوة."
        )

        llm_client = get_llm_client()
        writer = self._get_writer()
        try:
            if writer is not None:
                # D-048 + ISS-STREAM-002: STREAMING — يبث token-by-token عبر custom event
                # D-061 (ISS-074): تطبيع LaTeX على الـ chunks قبل الإرسال
                # D-064 (ISS-076): تنظيف foreign-script + meta-narration
                stream_messages = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ]
                normalizer = LatexStreamNormalizer()
                parts: list[str] = []
                async for chunk in llm_client.stream_chat(stream_messages):
                    try:
                        # ISS-STREAM-002: extract_stream_content يدعم ChatCompletionChunk و dict
                        content = llm_client.extract_stream_content(chunk)
                        if not content:
                            continue
                        for safe_chunk in normalizer.feed(content):
                            # ISS-078 D-066: sanitize chunk قبل إرساله للعميل
                            # يمنع Chinese/Russian/Japanese من الظهور لحظياً
                            sanitized = sanitize_chunk(safe_chunk)
                            if not sanitized:
                                continue
                            parts.append(sanitized)
                            writer(
                                {
                                    "chunk_type": "assistant_delta",
                                    "content": sanitized,
                                    "node": "chat_fallback",
                                }
                            )
                    except Exception:
                        continue
                for tail_chunk in normalizer.flush():
                    sanitized_tail = sanitize_chunk(tail_chunk)
                    if not sanitized_tail:
                        continue
                    parts.append(sanitized_tail)
                    writer(
                        {
                            "chunk_type": "assistant_delta",
                            "content": sanitized_tail,
                            "node": "chat_fallback",
                        }
                    )
                streamed = "".join(parts).strip()
                if streamed:
                    fallback_response = streamed
            else:
                # ISS-STREAM-002: استخدام llm_client.generate() بدل ai_client.send_message()
                resp = await llm_client.generate(
                    messages=[
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.7,
                )
                raw = resp.choices[0].message.content or ""
                # D-061: تطبيع LaTeX حتى في non-streaming path
                response_content = normalize_latex(raw)
                if response_content and response_content.strip():
                    fallback_response = response_content.strip()
        except Exception as error:
            emit_telemetry(
                node_name="ChatFallbackNode",
                start_time=start_time,
                state=state,
                error=error,
            )

        # ─── D-064 (ISS-076): تنظيف foreign-script + chat meta-narration ────
        fallback_response = sanitize_response(fallback_response, intent="chat")

        emit_telemetry(node_name="ChatFallbackNode", start_time=start_time, state=state)

        from langchain_core.messages import AIMessage

        return {
            "final_response": fallback_response,
            "messages": [AIMessage(content=fallback_response)],
        }


class QueryRewriterSignature(dspy.Signature):
    # CONTEXT_FIX: توقيع مقيد بقواعد صارمة لضمان إعادة كتابة آمنة ومختصرة.
    """Rewrite the current query into a self-contained standalone query.

    Rules:
    1) Resolve pronouns and implicit references using conversation history only.
    2) Preserve user intent exactly; do not answer or expand semantics.
    3) Keep the same user language (Arabic/English/mixed).
    4) If the query is already self-contained, return it unchanged.
    5) Keep rewrite concise and free of transcript labels.
    """

    conversation_history: str = dspy.InputField(
        desc="Recent turns formatted as User/Assistant transcript"
    )
    current_query: str = dspy.InputField(desc="Current possibly ambiguous user query")
    rewritten_query: str = dspy.OutputField(
        desc="Self-contained rewritten query or unchanged original query"
    )


class QueryRewriterNode:
    # CONTEXT_FIX: عقدة حل إحالات ضميرية مع بوابة سريعة + fallback آمن.
    def __init__(self) -> None:
        self.rewriter = dspy.ChainOfThought(QueryRewriterSignature)
        self.logger = logging.getLogger("graph")

    def _needs_rewrite(self, query: str, messages: list[object]) -> bool:
        # CONTEXT_FIX: بوابة حتمية سريعة تمنع استدعاء LLM عند عدم الحاجة.
        """يحدد إذا كان السؤال يحتاج إعادة صياغة مرجعية قبل البحث."""
        if not query.strip() or not messages:
            return False

        query_words = _tokenize_query(query)
        for word in query_words:
            for suffix in ARABIC_PRONOUN_SUFFIXES:
                if word.endswith(suffix) and len(word) > len(suffix) + 1:
                    return True

        if _contains_anaphora_indicator(query=query):
            return True

        history = build_conversation_context(messages=messages)
        if _looks_elliptical_followup(query=query, history=history):
            return True

        return len(query_words) <= 5 and bool(history.strip())

    def _is_valid_rewrite(
        self,
        original_query: str,
        rewritten_query: str,
        conversation_history: str,
    ) -> bool:
        # CONTEXT_FIX: تحقق صارم لمنع تسريب صيغة السجل أو التضخم غير المبرر.
        """يتحقق من صلاحية إعادة الصياغة قبل تمريرها لعقد التحليل."""
        candidate = rewritten_query.strip()
        original = original_query.strip()
        if not candidate:
            return False
        if candidate in conversation_history:
            return False
        if len(candidate) > max(24, len(original) * 3):
            return False
        return "User:" not in candidate and "Assistant:" not in candidate

    def _extract_latest_reference_snippet(self, messages: list[object], current_query: str) -> str:
        """يستخرج آخر رسالة مرجعية غير فارغة لتثبيت الإحالة الضميرية عند الفشل."""
        if not messages:
            return ""

        current_query_normalized = current_query.strip()

        for message in reversed(messages):  # include all messages to avoid context amnesia
            role = get_message_role(message)
            content = get_message_content(message)
            if role not in {"user", "assistant"}:
                continue
            if isinstance(content, str) and content.strip() == current_query_normalized:
                continue

            # Try extracting from structured kwargs first
            if isinstance(message, dict):
                additional = message.get("additional_kwargs", {})
            else:
                additional = getattr(message, "additional_kwargs", {})
            if isinstance(additional, dict) and "structured" in additional:
                structured = additional["structured"]
                if isinstance(structured, dict):
                    text = structured.get("الإجابة") or str(structured)
                    if text and len(text) <= 220:
                        return text[:220].strip()

            if not isinstance(content, str):
                continue
            text = content.strip()
            # Context blindness fix: try extracting the core text if the response was JSON-encoded by LangGraph
            if text.startswith("{") and role in {"ai", "assistant"}:
                try:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        extracted = data.get("الإجابة") or data.get("التمرين") or text
                        text = str(extracted).strip()
                except Exception:
                    pass
            if not text:
                continue
            if len(text) > 220:
                return text[:220].strip()
            return text
        return ""

    def _build_contextual_fallback_rewrite(self, query: str, messages: list[object]) -> str:
        """يبني إعادة صياغة حتمية عند تعذر إعادة الصياغة الذكية لمنع عمى السياق."""
        reference = self._extract_latest_reference_snippet(messages=messages, current_query=query)
        if not reference:
            return query

        lowered = query.casefold()
        if any(token in lowered for token in ["capital", "عاصمة"]):
            return f"اعتمادًا على هذا السياق: {reference}\nالسؤال الحالي: {query}"

        if _contains_anaphora_indicator(query=query) or _looks_elliptical_followup(
            query=query,
            history=build_conversation_context(messages=messages),
        ):
            return f"بالرجوع إلى آخر سياق في نفس المحادثة: {reference}\nالسؤال: {query}"
        return query

    async def __call__(self, state: AgentState) -> dict:
        # CONTEXT_FIX: تنفيذ غير حاجب مع fallback آمن إلى السؤال الأصلي.
        """يعيد كتابة السؤال الغامض إلى صيغة مستقلة قبل دخوله مسار البحث."""
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        query = str(state.get("query", "")).strip()
        logger.debug("QueryRewriterNode query=%.80s", query)
        messages = state.get("messages", [])
        # D-103: مع محتوى تمرين محقون لا حاجة لإعادة الصياغة المرجعية —
        # الاسترجاع سيتجاوز البحث ويستخدم المحتوى المحقون مباشرة (يوفّر LLM call).
        if str(state.get("exercise_content") or "").strip():
            emit_telemetry(node_name="QueryRewriterNode", start_time=start_time, state=state)
            return {"query": query}
        if not query or len(messages) <= 1:
            emit_telemetry(node_name="QueryRewriterNode", start_time=start_time, state=state)
            return {"query": query}

        if not self._needs_rewrite(query=query, messages=messages):
            emit_telemetry(node_name="QueryRewriterNode", start_time=start_time, state=state)
            return {"query": query}

        history = build_conversation_context(messages=messages)
        if not history.strip():
            emit_telemetry(node_name="QueryRewriterNode", start_time=start_time, state=state)
            return {"query": query}

        rewritten_query = query
        try:
            result = await asyncio.to_thread(
                self.rewriter,
                conversation_history=history,
                current_query=query,
            )
            candidate = getattr(result, "rewritten_query", "")
            if isinstance(candidate, str) and self._is_valid_rewrite(query, candidate, history):
                rewritten_query = candidate.strip()
        except Exception as error:
            self.logger.debug("QueryRewriterNode fallback to original query: %s", error)
            emit_telemetry(
                node_name="QueryRewriterNode",
                start_time=start_time,
                state=state,
                error=error,
            )
            return {
                "query": self._build_contextual_fallback_rewrite(query=query, messages=messages)
            }

        if rewritten_query == query:
            rewritten_query = self._build_contextual_fallback_rewrite(
                query=query, messages=messages
            )

        emit_telemetry(node_name="QueryRewriterNode", start_time=start_time, state=state)
        return {"query": rewritten_query}


class ToolExecutorNode:
    async def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        logger.debug("ToolExecutorNode query=%.80s", str(state.get("query", "")).strip())
        messages = state.get("messages", [])
        if not messages:
            emit_telemetry(node_name="ToolExecutorNode", start_time=start_time, state=state)
            return {"tools_executed": False}

        last_msg = messages[-1]
        results = []
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                from microservices.orchestrator_service.src.contracts.admin_tools import ADMIN_TOOLS

                for t in ADMIN_TOOLS:
                    if t.name == tc["name"]:
                        try:
                            if asyncio.iscoroutinefunction(t.invoke):
                                res = await t.ainvoke(tc["args"])
                            else:
                                res = t.invoke(tc["args"])
                            results.append(str(res))
                        except Exception as e:
                            results.append(f"Error: {e!s}")
                            emit_telemetry(
                                node_name="ToolExecutorNode",
                                start_time=start_time,
                                state=state,
                                error=e,
                            )

        emit_telemetry(
            node_name="ToolExecutorNode", start_time=start_time, state=state, tool_invoked=True
        )
        from langchain_core.messages import AIMessage

        return {
            "final_response": "\n".join(results),
            "tools_executed": True,
            "messages": [AIMessage(content="\n".join(results))],
        }


class ValidatorNode:
    def __call__(self, state: AgentState) -> dict:
        """يتحقق من اكتمال الحالة ويعيد تحديثًا غير فارغ لتلبية عقدة LangGraph."""
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        logger.debug("ValidatorNode query=%.80s", str(state.get("query", "")).strip())

        updates: dict[str, object] = {"tools_executed": bool(state.get("tools_executed", False))}

        final_response = state.get("final_response")
        is_failure = False
        if not final_response:
            is_failure = True
        elif isinstance(final_response, str):
            response_lower = final_response.lower()
            failure_phrases = ["لم أفهم", "يرجى التوضيح", "لا أستطيع"]
            if (
                any(phrase in response_lower for phrase in failure_phrases)
                or not response_lower.strip()
            ):
                is_failure = True

        retry_count = state.get("retry_count", 0)
        if is_failure:
            if retry_count >= 1:
                updates["final_response"] = "عذراً، لم أتمكن من معالجة السياق."
                updates["retry_count"] = retry_count
            else:
                updates["retry_count"] = retry_count + 1

        emit_telemetry(node_name="ValidatorNode", start_time=start_time, state=state)
        return updates

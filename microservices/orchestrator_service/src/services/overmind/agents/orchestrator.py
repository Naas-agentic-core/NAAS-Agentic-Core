"""
Orchestrator Agent (Ported).
"""

import contextlib
import json
import re
from collections.abc import AsyncGenerator

from microservices.orchestrator_service.src.core.logging import get_logger
from microservices.orchestrator_service.src.services.llm.client import AIClient
from microservices.orchestrator_service.src.services.overmind.agents.admin import AdminAgent
from microservices.orchestrator_service.src.services.overmind.agents.analytics import (
    AnalyticsAgent,
)
from microservices.orchestrator_service.src.services.overmind.agents.curriculum import (
    CurriculumAgent,
)
from microservices.orchestrator_service.src.services.overmind.agents.data_access import (
    DataAccessAgent,
)
from microservices.orchestrator_service.src.services.overmind.agents.education_council import (
    EducationCouncil,
)
from microservices.orchestrator_service.src.services.overmind.agents.memory import MemoryAgent
from microservices.orchestrator_service.src.services.overmind.agents.refactor import (
    RefactorAgent,
)
from microservices.orchestrator_service.src.services.overmind.domain.writer_intent import (
    WriterIntent,
)
from microservices.orchestrator_service.src.services.overmind.utils.context import (
    InMemoryCollaborationContext,
)
from microservices.orchestrator_service.src.services.overmind.utils.context_composer import (
    _extract_requested_index,
    _extract_section_by_index,
)
from microservices.orchestrator_service.src.services.overmind.utils.context_service import (
    get_context_service,
)
from microservices.orchestrator_service.src.services.overmind.utils.intent_detector import (
    ChatIntent,
    IntentDetector,
)
from microservices.orchestrator_service.src.services.overmind.utils.mission_complex import (
    handle_mission_complex_stream,
)
from microservices.orchestrator_service.src.services.overmind.utils.regex_intent_detector import (
    RegexIntentDetector,
)
from microservices.orchestrator_service.src.services.overmind.utils.tools import ToolRegistry

logger = get_logger("orchestrator-agent")


def _extract_marking_scheme_blocks(content: str) -> list[str]:
    """
    استخراج كتل سلم التنقيط من النص الخام إذا كانت مضمّنة.
    """
    patterns = [
        r"(?is)\n\[(grading|marking|rubric):[^\]]+\][\s\S]+?(?=\n\s*\[(ex|exercise|sol|solution):|$)",
        r"(?i)\n(#{1,3}\s*(سلم التنقيط|سلم التصحيح|marking scheme|grading scheme))[\s\S]+?(?=\n\s*\*{0,2}(#{1,3}|Exercise|Question|السؤال|تمرين|التمرين)|$)",
    ]
    extracted: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, content, flags=re.DOTALL):
            block = match.group(0).strip()
            if block and block not in extracted:
                extracted.append(block)
    return extracted


class OrchestratorRunResult:
    """
    Orchestrator run result that supports async iteration and awaitable string.
    """

    def __init__(self, stream: AsyncGenerator[str, None]) -> None:
        self._stream = stream

    def __aiter__(self) -> AsyncGenerator[str, None]:
        return self._stream

    def __await__(self):
        async def _collect() -> str:
            chunks: list[str] = []
            async for chunk in self._stream:
                chunks.append(chunk)
            return "".join(chunks)

        return _collect().__await__()


class OrchestratorAgent:
    """
    Orchestrator Agent (Microservice Edition).
    """

    def __init__(self, ai_client: AIClient, tools: ToolRegistry) -> None:
        self.ai_client = ai_client
        self.tools = tools
        self.intent_detector = IntentDetector()

        # Sub-Agents
        self.admin_agent = AdminAgent(tools, ai_client=ai_client)
        self.analytics_agent = AnalyticsAgent(tools, ai_client)
        self.curriculum_agent = CurriculumAgent(tools)
        self.memory_agent = MemoryAgent()
        self.education_council = EducationCouncil(tools)

    @property
    def data_agent(self) -> DataAccessAgent:
        return self.admin_agent.data_agent

    @data_agent.setter
    def data_agent(self, value: DataAccessAgent) -> None:
        self.admin_agent.data_agent = value

    @property
    def refactor_agent(self) -> RefactorAgent:
        return self.admin_agent.refactor_agent

    @refactor_agent.setter
    def refactor_agent(self, value: RefactorAgent) -> None:
        self.admin_agent.refactor_agent = value

    def run(self, question: str, context: dict[str, object] | None = None) -> OrchestratorRunResult:
        """
        Unified entrypoint for streaming processing.
        """
        return OrchestratorRunResult(self._run_stream(question, context))

    async def _run_stream(
        self,
        question: str,
        context: dict[str, object] | None = None,
    ) -> AsyncGenerator[str, None]:
        logger.info(f"Orchestrator received: {question}")
        normalized = question.strip()
        context = context or {}

        # 1. Intent Detection
        intent = None
        if "intent" in context:
            val = context["intent"]
            if isinstance(val, ChatIntent):
                intent = val
            elif isinstance(val, str):
                with contextlib.suppress(ValueError):
                    intent = ChatIntent(val)

        if not intent:
            intent_result = await self.intent_detector.detect(normalized)
            intent = intent_result.intent

        # 2. Memory Capture (Best Effort)
        await self._capture_memory_intent(normalized, intent)

        # 3. Dispatch
        try:
            if intent in {ChatIntent.ADMIN_QUERY, ChatIntent.CODE_SEARCH, ChatIntent.PROJECT_INDEX}:
                async for chunk in self._as_json_event(self.admin_agent.run(normalized, context)):
                    yield chunk

            elif intent == ChatIntent.MISSION_COMPLEX:
                # Ensure user_id is present for mission creation security
                if "user_id" not in context:
                    yield self._make_json_event("❌ خطأ أمني: معرف المستخدم مفقود.")
                    return
                user_id = int(context["user_id"])
                async for chunk in handle_mission_complex_stream(normalized, context, user_id):
                    yield self._serialize_mission_chunk(chunk)

            elif intent in (ChatIntent.ANALYTICS_REPORT, ChatIntent.LEARNING_SUMMARY):
                result = self.analytics_agent.process(context)
                if hasattr(result, "__aiter__"):
                    async for chunk in self._as_json_event(result):
                        yield chunk
                else:
                    yield self._make_json_event(str(result))

            elif intent == ChatIntent.CURRICULUM_PLAN:
                self._enrich_curriculum_context(context, normalized)
                context["user_message"] = normalized
                result = self.curriculum_agent.process(context)
                if hasattr(result, "__aiter__"):
                    async for chunk in self._as_json_event(result):
                        yield chunk
                else:
                    yield self._make_json_event(str(result))

            elif intent == ChatIntent.CONTENT_RETRIEVAL:
                async for chunk in self._as_json_event(
                    self._handle_content_retrieval(normalized, context)
                ):
                    yield chunk

            else:
                async for chunk in self._as_json_event(
                    self._handle_chat_fallback(normalized, context)
                ):
                    yield chunk

        except Exception as e:
            logger.error(f"Orchestrator dispatch failed: {e}", exc_info=True)
            yield self._make_json_event("عذرًا، حدث خطأ غير متوقع أثناء معالجة طلبك.")

    def _make_json_event(self, text: str) -> str:
        return json.dumps({"type": "assistant_delta", "payload": {"content": text}}) + "\n"

    def _serialize_mission_chunk(self, chunk: dict[str, object] | str) -> str:
        """يضمن أن مخرجات mission_complex تُبث كسلاسل نصية قابلة للترميز عبر StreamingResponse."""
        if isinstance(chunk, str):
            return chunk if chunk.endswith("\n") else f"{chunk}\n"
        return json.dumps(chunk, ensure_ascii=False) + "\n"

    async def _as_json_event(
        self, generator: AsyncGenerator[str, None]
    ) -> AsyncGenerator[str, None]:
        async for chunk in generator:
            yield self._make_json_event(chunk)

    async def _capture_memory_intent(self, question: str, intent: ChatIntent) -> None:
        if not self.memory_agent:
            return
        try:
            collab_context = InMemoryCollaborationContext({"intent": intent.value})
            await self.memory_agent.capture_memory(
                collab_context,
                label="user_intent",
                payload={"question": question, "intent": intent.value},
            )
        except Exception as e:
            logger.warning(f"Memory capture failed: {e}")

    def _enrich_curriculum_context(self, context: dict, question: str) -> None:
        lowered = question.lower()
        if any(x in lowered for x in ["مسار", "path", "تقدم", "progress"]):
            context["intent_type"] = "path_progress"
        elif any(x in lowered for x in ["صعب", "hard", "easy", "سهل"]):
            context["intent_type"] = "difficulty_adjust"
            context["feedback"] = "too_hard" if "صعب" in lowered else "good"
        else:
            context["intent_type"] = "recommendation"

    async def _handle_content_retrieval(
        self, question: str, context: dict
    ) -> AsyncGenerator[str, None]:
        logger.info(f"Handling content retrieval for: {question}")

        params = await self._ai_extract_search_params(question)

        candidates = await self.tools.execute("search_content", params)

        if not candidates:
            logger.info("No content found for query, falling back to smart tutor.")
            context["search_miss"] = True
            async for chunk in self._handle_chat_fallback(question, context):
                yield chunk
            return

        # Pick the best candidate (Top 1)
        best_candidate = candidates[0]
        content_id = best_candidate["id"]
        title = best_candidate["title"]

        yield f"✅ **تم العثور على:** {title} ({content_id})\n\n"

        writer_intent = RegexIntentDetector().analyze(question)

        include_solution = writer_intent in (
            WriterIntent.SOLUTION_REQUEST,
            WriterIntent.GRADING_REQUEST,
        )
        exclude_solution = writer_intent == WriterIntent.QUESTION_ONLY_REQUEST
        include_grading = writer_intent == WriterIntent.GRADING_REQUEST

        logger.info(
            f"Writer intent: {writer_intent}, include_solution: {include_solution}, exclude_solution: {exclude_solution}"
        )

        raw_data = await self.tools.execute(
            "get_content_raw",
            {
                "content_id": content_id,
                "include_solution": include_solution and not exclude_solution,
            },
        )

        if raw_data and raw_data.get("content"):
            full_content = raw_data["content"]
            content_text = full_content
            requested_index = _extract_requested_index(question)
            if requested_index is not None:
                extracted = _extract_section_by_index(full_content, requested_index)
                if extracted:
                    content_text = extracted
            yield "---\n\n"
            yield content_text
            yield "\n\n---\n\n"

            if include_solution and not exclude_solution:
                personalization_context = await self._build_education_brief(context)
                solution = raw_data.get("solution")

                async for chunk in self._generate_explanation(
                    question, content_text, personalization_context, solution=solution
                ):
                    yield chunk
            if include_grading and not exclude_solution:
                grading_blocks = _extract_marking_scheme_blocks(full_content)
                if grading_blocks:
                    yield "\n\n### سلم التنقيط (Marking Scheme):\n"
                    yield "\n\n".join(grading_blocks)
                else:
                    yield "\n\n⚠️ لم يتم العثور على سلم التنقيط في نص المحتوى."
            else:
                yield "هل ترغب أن أقدّم الحل أو تفضّل المحاولة أولاً؟"
        else:
            yield "عذراً، تعذر تحميل نص المحتوى."

    async def _ai_extract_search_params(self, question: str) -> dict:
        system_prompt = (
            "You are a search query parser for an educational database. "
            "Extract parameters from the user's request into a JSON object. "
            "Fields: q (keywords - EXTRACT THE TOPIC), year (int), subject (Mathematics, Physics), "
            "branch (experimental_sciences, math_tech, etc), set_name, level, type (exercise, lesson). "
            "\n\nIMPORTANT RULES:"
            "\n1. 'q' MUST contain the actual TOPIC/SUBJECT being searched, NOT the full question!"
            "\n2. Topics examples:"
            "\n   - 'probability' (احتمالات), 'complex numbers' (أعداد مركبة), 'sequences' (متتاليات)"
            "\n   - 'functions' (دوال), 'derivatives' (مشتقات), 'integrals' (تكامل)"
            "\n   - 'limits' (نهايات), 'continuity' (استمرارية), 'geometry' (هندسة)"
            "\n3. 'Subject 1' -> set_name: 'subject_1', 'Subject 2' -> set_name: 'subject_2'."
            "\n4. 'Experimental Sciences' (علوم تجريبية) -> branch: 'experimental_sciences'."
            "\n5. If a field is not present, omit it."
            "\n\nEXAMPLES:"
            "\n- 'تمرين أعداد مركبة' -> {'q': 'complex numbers'}"
            "\n- 'احتمالات بكالوريا 2024' -> {'q': 'probability', 'year': 2024, 'level': 'baccalaureate'}"
            "\n- 'متتاليات علوم تجريبية' -> {'q': 'sequences', 'branch': 'experimental_sciences'}"
            "\n- 'دوال أسية' -> {'q': 'exponential functions'}"
            "\n- 'نهايات ودوال' -> {'q': 'limits functions'}"
            "\n- 'سحب كرة' -> {'q': 'probability'} (this is about drawing balls = probability)"
        )

        try:
            response = await self.ai_client.generate(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            params = json.loads(content)
            params["limit"] = 5

            if not params.get("q") and not params.get("year"):
                params = self._heuristic_extract_search_params(question)

            logger.info(f"AI extracted params: {params}")
            return params

        except Exception as e:
            logger.warning(f"AI parameter extraction failed: {e}. using heuristics.")
            return self._heuristic_extract_search_params(question)

    def _heuristic_extract_search_params(self, question: str) -> dict:
        params = {"limit": 5}
        q_lower = question.lower()

        topic_map = {
            "أعداد مركبة": "complex numbers",
            "اعداد مركبة": "complex numbers",
            "مركب": "complex numbers",
            "احتمال": "probability",
            "احتمالات": "probability",
            "سحب": "probability",
            "كرة": "probability",
            "كرات": "probability",
            "متتالي": "sequences",
            "متتاليات": "sequences",
            "دوال": "functions",
            "دالة": "functions",
            "نهاي": "limits",
            "نهايات": "limits",
            "تكامل": "integrals",
            "مشتق": "derivatives",
            "استمرار": "continuity",
            "هندس": "geometry",
            "أسية": "exponential",
            "لوغاريتم": "logarithm",
            "complex": "complex numbers",
            "probability": "probability",
            "sequence": "sequences",
            "function": "functions",
            "limit": "limits",
            "integral": "integrals",
            "derivative": "derivatives",
            "continuity": "continuity",
            "geometry": "geometry",
        }

        for keyword, topic in topic_map.items():
            if keyword in q_lower:
                params["q"] = topic
                break

        if "q" not in params:
            stop_words = {"أريد", "أعطني", "اعطني", "هات", "التمرين", "تمرين", "بدون", "حل", "فقط"}
            words = [w for w in question.split() if w not in stop_words and len(w) > 2]
            params["q"] = " ".join(words[:3]) if words else question

        if "2024" in question:
            params["year"] = 2024
        elif "2023" in question:
            params["year"] = 2023
        elif "2022" in question:
            params["year"] = 2022

        if any(w in q_lower for w in ["math", "رياضيات", "رياضه"]):
            params["subject"] = "Mathematics"
        elif any(w in q_lower for w in ["physics", "فيزياء"]):
            params["subject"] = "Physics"

        logger.info(f"Heuristic extracted params: {params}")
        return params

    async def _generate_explanation(
        self, question: str, content: str, personalization_context: str, solution: str | None = None
    ) -> AsyncGenerator[str, None]:
        system_prompt = (
            "أنت 'Overmind'، المعلم الذكي فائق القدرات (Smart Tutor)."
            "\nمهمتك: تقديم شرح فاخر (Luxury)، عميق، ومبسط للتمرين المسترجع."
            "\n\nالتعليمات الصارمة:"
            "\n1. التزم كلياً بـ 'الحل الرسمي' (Official Solution) الموجود في السياق أدناه. هو المصدر الوحيد للحقيقة."
            "\n2. لا تكتفِ بسرد الحل؛ اشرح 'لماذا' و 'كيف' وصلنا لهذه النتيجة."
            "\n3. بسّط المفاهيم المعقدة لتناسب طالباً ذا قدرات محدودة، لكن بأسلوب راقٍ واحترافي."
            "\n4. إذا لم يوجد حل رسمي، استخدم خبرتك لشرح المفهوم دون اختراع أرقام."
            "\n5. الهدف: جعل الطالب يفهم أعمق التفاصيل بسهولة تامة."
        )

        if personalization_context:
            system_prompt += f"\n\nمرجع الجودة التعليمية الموحد:\n{personalization_context}"

        user_message = f"سؤال الطالب: {question}\n\n"
        user_message += f"نص التمرين (Exercise):\n{content}\n\n"

        if solution:
            user_message += (
                f"الحل الرسمي (Official Solution - STRICTLY ADHERE TO THIS):\n{solution}\n\n"
            )
        else:
            user_message += "ملاحظة: لا يوجد حل رسمي مسجل. اشرح المفهوم العام فقط.\n\n"

        user_message += "المطلوب: اشرح الحل للطالب بأسلوب 'Smart Tutor' (عميق، مبسط، واحترافي)."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        async for chunk in self._stream_ai_chunks(messages):
            if hasattr(chunk, "choices"):
                delta = chunk.choices[0].delta if chunk.choices else None
                content = delta.content if delta else ""
            else:
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")

            if content:
                yield content

    async def _handle_chat_fallback(
        self, question: str, context: dict
    ) -> AsyncGenerator[str, None]:
        system_context = context.get("system_context", "")

        try:
            base_prompt = get_context_service().get_customer_system_prompt()
        except Exception:
            base_prompt = "أنت مساعد ذكي."

        strict_instruction = (
            "\nأنت معلم ذكي ومحترف (Smart Tutor)."
            "\nالقواعد الصارمة:"
            "\n1. إذا توفر محتوى تمرين في السياق (SIAQ)، التزم به حرفياً."
            "\n2. إذا لم يتوفر تمرين، اشرح المفهوم العلمي/الرياضي بشكل عام (General Concept) وشامل."
            "\n3. ممنوع منعاً باتاً اختراع تمارين أو أرقام من خيالك. قل 'لا يوجد تمرين محدد، لكن الفكرة هي...'."
            "\n4. اشرح 'لماذا' و 'كيف' دائماً لتبسيط التعقيدات."
        )

        personalization_context = await self._build_education_brief(context)

        history_msgs = context.get("history_messages", [])
        history_text = ""
        if history_msgs:
            recent = history_msgs[-10:]
            history_text = "\nSIAQ (History):\n" + "\n".join(
                [f"{m.get('role')}: {m.get('content')}" for m in recent]
            )

        personalization_block = ""
        if personalization_context:
            personalization_block = f"\nمرجع الجودة:\n{personalization_context}"
        final_prompt = f"{base_prompt}\n{strict_instruction}{personalization_block}\n{system_context}\n{history_text}"

        messages = [
            {"role": "system", "content": final_prompt},
            {"role": "user", "content": question},
        ]

        async for chunk in self._stream_ai_chunks(messages):
            if hasattr(chunk, "choices"):
                delta = chunk.choices[0].delta if chunk.choices else None
                content = delta.content if delta else ""
            else:
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")

            if content:
                yield content

    async def _build_education_brief(self, context: dict[str, object]) -> str:
        cached_context = context.get("education_brief")
        if isinstance(cached_context, str):
            return cached_context

        try:
            brief = await self.education_council.build_brief(context=context)
        except Exception as exc:
            logger.warning("Failed to build education brief: %s", exc)
            return ""

        rendered = brief.render()
        context["education_brief"] = rendered
        return rendered

    async def _stream_ai_chunks(
        self,
        messages: list[dict[str, str]],
    ) -> AsyncGenerator[object, None]:
        if not self.ai_client:
            raise RuntimeError("عميل الذكاء الاصطناعي غير متوفر.")
        stream_result = self.ai_client.stream_chat(messages)
        if hasattr(stream_result, "__await__"):
            stream_result = await stream_result
        async for chunk in stream_result:
            yield chunk

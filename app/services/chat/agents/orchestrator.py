import json
import logging
import re
from collections.abc import AsyncGenerator

from app.core.ai_gateway import AIClient
from app.services.chat.agents.admin import AdminAgent
from app.services.chat.agents.analytics import AnalyticsAgent
from app.services.chat.agents.curriculum import CurriculumAgent
from app.services.chat.agents.data_access import DataAccessAgent
from app.services.chat.agents.education_council import EducationCouncil
from app.services.chat.agents.refactor import RefactorAgent
from app.services.chat.context_service import get_context_service
from app.services.chat.graph.components.context_composer import (
    _extract_requested_index,
    _extract_section_by_index,
)
from app.services.chat.graph.components.intent_detector import RegexIntentDetector
from app.services.chat.graph.domain import WriterIntent
from app.services.chat.intent_detector import ChatIntent, IntentDetector
from app.services.chat.tools import ToolRegistry

logger = logging.getLogger("orchestrator-agent")


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
    نتيجة تشغيل وكيل التنسيق.

    تدعم البث عبر التكرار غير المتزامن، كما تسمح بانتظار النتيجة كنص كامل.
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
    الوكيل المنسق (Orchestrator Agent).

    يعمل كنقطة دخول مركزية لتوجيه الطلبات إلى الوكلاء المتخصصين.
    يدعم استرجاع المحتوى الدقيق باستخدام الأدوات الجديدة والبحث الدلالي.
    """

    def __init__(self, ai_client: AIClient, tools: ToolRegistry) -> None:
        self.ai_client = ai_client
        self.tools = tools
        self.intent_detector = IntentDetector()

        # Sub-Agents
        self.admin_agent = AdminAgent(tools, ai_client=ai_client)
        self.analytics_agent = AnalyticsAgent(tools, ai_client)
        self.curriculum_agent = CurriculumAgent(tools)
        self.education_council = EducationCouncil(tools)

    @property
    def data_agent(self) -> DataAccessAgent:
        """إتاحة وكيل البيانات للوصول والاختبار."""
        return self.admin_agent.data_agent

    @data_agent.setter
    def data_agent(self, value: DataAccessAgent) -> None:
        self.admin_agent.data_agent = value

    @property
    def refactor_agent(self) -> RefactorAgent:
        """إتاحة وكيل التحسينات للوصول والاختبار."""
        return self.admin_agent.refactor_agent

    @refactor_agent.setter
    def refactor_agent(self, value: RefactorAgent) -> None:
        self.admin_agent.refactor_agent = value

    def run(self, question: str, context: dict[str, object] | None = None) -> OrchestratorRunResult:
        """
        واجهة موحدة لمعالجة الطلبات مع دعم البث أو التجميع النصي.
        """
        return OrchestratorRunResult(self._run_stream(question, context))

    async def _run_stream(
        self,
        question: str,
        context: dict[str, object] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        التنفيذ الفعلي لمسار البث.
        """
        logger.info(f"Orchestrator received: {question}")
        normalized = question.strip()
        context = context or {}
        normalized = self._resolve_contextual_reference(normalized, context)
        normalized = self._inject_recent_history_context(normalized, context)

        # 1. Intent Detection
        if "intent" in context and isinstance(context["intent"], ChatIntent):
            intent = context["intent"]
        else:
            intent_result = await self.intent_detector.detect(normalized)
            intent = intent_result.intent

        # 2. Memory Capture (Best Effort)
        await self._capture_memory_intent(normalized, intent)

        # 3. Dispatch
        try:
            if intent in {ChatIntent.ADMIN_QUERY, ChatIntent.CODE_SEARCH, ChatIntent.PROJECT_INDEX}:
                async for chunk in self.admin_agent.run(normalized, context):
                    yield chunk

            elif intent in (ChatIntent.ANALYTICS_REPORT, ChatIntent.LEARNING_SUMMARY):
                result = self.analytics_agent.process(context)
                if hasattr(result, "__aiter__"):
                    async for chunk in result:
                        yield chunk
                else:
                    yield str(result)

            elif intent == ChatIntent.CURRICULUM_PLAN:
                self._enrich_curriculum_context(context, normalized)
                context["user_message"] = normalized
                result = self.curriculum_agent.process(context)
                if hasattr(result, "__aiter__"):
                    async for chunk in result:
                        yield chunk
                else:
                    yield str(result)

            elif intent == ChatIntent.CONTENT_RETRIEVAL:
                async for chunk in self._handle_content_retrieval(normalized, context):
                    yield chunk

            else:
                async for chunk in self._handle_chat_fallback(normalized, context):
                    yield chunk

        except Exception as e:
            logger.error(f"Orchestrator dispatch failed: {e}", exc_info=True)
            yield "عذرًا، حدث خطأ غير متوقع أثناء معالجة طلبك."

    async def _capture_memory_intent(self, question: str, intent: ChatIntent) -> None:
        pass

    def _enrich_curriculum_context(self, context: dict, question: str) -> None:
        lowered = question.lower()
        if any(x in lowered for x in ["مسار", "path", "تقدم", "progress"]):
            context["intent_type"] = "path_progress"
        elif any(x in lowered for x in ["صعب", "hard", "easy", "سهل"]):
            context["intent_type"] = "difficulty_adjust"
            context["feedback"] = "too_hard" if "صعب" in lowered else "good"
        else:
            context["intent_type"] = "recommendation"

    def _resolve_contextual_reference(self, question: str, context: dict[str, object]) -> str:
        """
        يحل الضمائر المرجعية القصيرة اعتماداً على آخر رسالة مستخدم في السياق.

        يهدف هذا التابع لتقليل حالات "العمى السياقي" عندما يرسل المستخدم
        أسئلة مختصرة مثل: "ما هي عاصمتها؟" بعد ذكر كيان واضح في الرسالة السابقة.
        """
        trimmed_question = question.strip()
        if not trimmed_question:
            return trimmed_question
        if not self._looks_like_pronoun_followup(trimmed_question):
            return trimmed_question

        anchor_message = self._extract_context_anchor(
            context=context,
            current_question=trimmed_question,
        )
        if not anchor_message:
            return trimmed_question

        return f"{trimmed_question}\n\nمرجع سياقي إلزامي من الرسائل السابقة: {anchor_message}"

    def _extract_context_anchor(
        self,
        *,
        context: dict[str, object],
        current_question: str,
    ) -> str | None:
        """
        يستخرج مرجعًا سياقيًا موثوقًا من history_messages مع استبعاد السؤال الحالي.
        """
        history_value = context.get("history_messages")
        if not isinstance(history_value, list):
            return None

        normalized_current = current_question.strip().casefold()
        skipped_current_user = False
        for item in reversed(history_value):
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = item.get("content")
            if not isinstance(content, str):
                continue
            cleaned = content.strip()
            if not cleaned:
                continue
            if (
                role == "user"
                and not skipped_current_user
                and cleaned.casefold() == normalized_current
            ):
                skipped_current_user = True
                continue
            return cleaned
        return None

    def _looks_like_pronoun_followup(self, question: str) -> bool:
        """
        يتحقق ما إذا كان السؤال يعتمد غالباً على ضمير مرجعي يحتاج سياقاً سابقاً.
        """
        lowered = question.casefold()
        pronoun_markers = (
            "ها",
            "عاصمتها",
            "سكانها",
            "مساحتها",
            "موقعها",
            "علمها",
            "اقتصادها",
            "تاريخها",
        )
        if any(marker in lowered for marker in pronoun_markers):
            return True
        demonstratives = ("هذا", "هذه", "ذلك", "تلك", "هاته", "this", "that", "there")
        referential_nouns = (
            "الدولة",
            "البلد",
            "المدينة",
            "الكيان",
            "الدالة",
            "المعادلة",
            "التمرين",
            "السؤال",
            "function",
            "equation",
            "problem",
        )
        if any(word in lowered for word in demonstratives) and any(
            noun in lowered for noun in referential_nouns
        ):
            return True
        return lowered.startswith(("كيف جاءت", "كيف حصل", "كيف صارت", "لماذا جاءت"))

    def _inject_recent_history_context(self, question: str, context: dict[str, object]) -> str:
        """
        يحقن موجزًا من التاريخ الحديث لإبقاء وعي السياق فعالًا في كل الأسئلة.
        """
        history_brief = self._build_recent_history_brief(context=context, current_question=question)
        if not history_brief:
            return question
        if "سياق المحادثة السابق (موجز)" in question:
            return question
        return f"سياق المحادثة السابق (موجز):\n{history_brief}\n\nالسؤال الحالي: {question}"

    def _build_recent_history_brief(
        self,
        *,
        context: dict[str, object],
        current_question: str,
    ) -> str:
        """
        يبني موجزًا مختصرًا من آخر الرسائل مع تجاهل السؤال الحالي.
        """
        history_value = context.get("history_messages")
        if not isinstance(history_value, list):
            return ""

        normalized_current = current_question.strip().casefold()
        items: list[str] = []
        skipped_current_user = False

        for item in reversed(history_value):
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = item.get("content")
            if not isinstance(content, str):
                continue
            cleaned = " ".join(content.split()).strip()
            if not cleaned:
                continue
            if (
                role == "user"
                and not skipped_current_user
                and cleaned.casefold() == normalized_current
            ):
                skipped_current_user = True
                continue
            role_label = "المستخدم" if role == "user" else "المساعد"
            items.append(f"- {role_label}: {cleaned[:220]}")
            if len(items) >= 4:
                break

        items.reverse()
        return "\n".join(items)

    async def _handle_content_retrieval(
        self, question: str, context: dict
    ) -> AsyncGenerator[str, None]:
        """
        معالجة استرجاع المحتوى:
        1. استخراج الفلاتر بذكاء (AI Extraction) من النص الطبيعي.
        2. البحث عن IDs باستخدام search_content (الذي يدعم الآن الكلمات المتعددة).
        3. جلب المحتوى الخام وعرضه.
        4. توليد الشرح.
        """
        logger.info(f"Handling content retrieval for: {question}")

        # Step 1: Intelligent Search Parameter Extraction using LLM
        params = await self._ai_extract_search_params(question)

        candidates = await self.tools.execute("search_content", params)

        if not candidates:
            logger.info("No content found for query, falling back to smart tutor.")
            # Inject a hint into context so fallback knows we missed a search
            context["search_miss"] = True
            async for chunk in self._handle_chat_fallback(question, context):
                yield chunk
            return

        # Pick the best candidate (Logic: Top 1)
        best_candidate = candidates[0]
        content_id = best_candidate["id"]
        title = best_candidate["title"]

        yield f"✅ **تم العثور على:** {title} ({content_id})\n\n"

        # Step 2: Determine if user wants solution
        writer_intent = RegexIntentDetector().analyze(question)

        # Logic: Only include solution if EXPLICITLY requested, NOT by default
        include_solution = writer_intent in (
            WriterIntent.SOLUTION_REQUEST,
            WriterIntent.GRADING_REQUEST,
        )
        exclude_solution = writer_intent == WriterIntent.QUESTION_ONLY_REQUEST
        include_grading = writer_intent == WriterIntent.GRADING_REQUEST

        # Log for debugging
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
                # Step 3: AI Explanation with Official Solution
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
        """
        Uses LLM to extract structured search parameters from natural language.
        Fallback to heuristics if LLM fails.
        """
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
            # Quick parsing call
            response = await self.ai_client.generate(
                model="gpt-4o-mini",  # Use a fast model if available, or default
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            params = json.loads(content)

            # Ensure limit default
            params["limit"] = 5

            # Fallback for 'q' if empty, use heuristic extraction
            if not params.get("q") and not params.get("year"):
                params = self._heuristic_extract_search_params(question)

            logger.info(f"AI extracted params: {params}")
            return params

        except Exception as e:
            logger.warning(f"AI parameter extraction failed: {e}. using heuristics.")
            return self._heuristic_extract_search_params(question)

    def _heuristic_extract_search_params(self, question: str) -> dict:
        """Fallback heuristic parameter extraction with topic detection."""
        params = {"limit": 5}
        q_lower = question.lower()

        # Topic detection (more specific)
        topic_map = {
            # Arabic topics
            "أعداد مركبة": "complex numbers",
            "اعداد مركبة": "complex numbers",
            "مركب": "complex numbers",
            "احتمال": "probability",
            "احتمالات": "probability",
            "سحب": "probability",  # سحب كرة = drawing = probability
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
            # English topics
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

        # Find the most specific topic
        for keyword, topic in topic_map.items():
            if keyword in q_lower:
                params["q"] = topic
                break

        # If no topic found, use cleaned question
        if "q" not in params:
            # Remove common request words, keep content words
            stop_words = {"أريد", "أعطني", "اعطني", "هات", "التمرين", "تمرين", "بدون", "حل", "فقط"}
            words = [w for w in question.split() if w not in stop_words and len(w) > 2]
            params["q"] = " ".join(words[:3]) if words else question

        logger.info(f"Heuristic extracted params: {params}")
        return params

    async def _generate_explanation(
        self, question: str, content: str, personalization_context: str, solution: str | None = None
    ) -> AsyncGenerator[str, None]:
        """
        توليد شرح أو تحليل للمحتوى المسترجع.
        يستخدم 'الحل الرسمي' (Official Solution) كمرجع أساسي (Source of Truth) إذا توفر.
        """

        # بناء التعليمات الأساسية (System Prompt)
        # نركز على كون الوكيل "Smart Tutor" يشرح بعمق ويبسط المعلومة بناءً على الحل الرسمي.

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

        # بناء رسالة المستخدم (Context Injection)
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
        """معالجة المحادثة العامة."""
        system_context = context.get("system_context", "")

        try:
            base_prompt = get_context_service().get_customer_system_prompt()
        except Exception:
            base_prompt = "أنت مساعد ذكي."

        # SMART TUTOR LOGIC
        # We permit general explanation if no specific exercise is loaded,
        # but strictly forbid fabricating specific numbers/exercises.
        strict_instruction = (
            "\nأنت معلم ذكي ومحترف (Smart Tutor)."
            "\nالقواعد الصارمة:"
            "\n1. إذا توفر محتوى تمرين في السياق (SIAQ)، التزم به حرفياً."
            "\n2. إذا لم يتوفر تمرين، اشرح المفهوم العلمي/الرياضي بشكل عام (General Concept) وشامل."
            "\n3. ممنوع منعاً باتاً اختراع تمارين أو أرقام من خيالك. قل 'لا يوجد تمرين محدد، لكن الفكرة هي...'."
            "\n4. اشرح 'لماذا' و 'كيف' دائماً لتبسيط التعقيدات."
        )

        personalization_context = await self._build_education_brief(context)

        # History
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
        """بناء موجز تعليمي."""
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
        """
        بث استجابات النموذج مع دعم نتائج قابلة للانتظار من AsyncMock.
        """
        if not self.ai_client:
            raise RuntimeError("عميل الذكاء الاصطناعي غير متوفر.")
        stream_result = self.ai_client.stream_chat(messages)
        if hasattr(stream_result, "__await__"):
            stream_result = await stream_result  # type: ignore[assignment]
        async for chunk in stream_result:
            yield chunk

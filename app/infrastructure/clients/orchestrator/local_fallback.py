"""Local fallback-chain mixin (D-166 Slice 4 — extracted verbatim from the God-file).

Single responsibility: the monolith's deterministic local responders — the fallback chain
that answers when the orchestrator microservice is unreachable or preempted: file-count
intelligence, indexed/DB exercise retrieval (Supabase candidate-gen + rerank), exercise
explanation-with-context streaming, question-only slicing, LangGraph local responses and
the general-chat streamer.

Mixed into `OrchestratorClient`; every `self._x` resolves through the MRO — behaviour is
byte-identical to the pre-extraction God-file (D-164 pattern: verbatim move, zero rewrite).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from app.core.ai_gateway import get_ai_client
from app.services.capabilities.exercise_retrieval import (
    ExerciseEntry,
    ExerciseRetrievalRequest,
    detect_explanation_with_context,
    format_exercise_for_display,
    load_exercise_content,
)
from app.services.capabilities.exercise_retrieval import (
    make_result as make_exercise_result,
)
from app.services.capabilities.file_intelligence import (
    count_project_files,
    default_project_root,
)
from app.services.capabilities.file_intelligence import (
    make_result as make_file_result,
)

# نفس اسم الـ logger القديم عمداً — استمرارية السجلات وصفر تغيير رصدي (نمط D-163/D-164).
logger = logging.getLogger("orchestrator-client")


class LocalFallbackMixin:
    """Deterministic local fallback chain — file-count / retrieval / explanation / general chat."""

    # M0: `_execute_shell_tool` حُذِف — كان الجسر الوحيد من مسار الدردشة الحيّ إلى
    # `execute_shell`، وقد زال مبرّره حين صار عدّ الملفات بايثون خالصة. قدرة بلا
    # مستهلك حيّ تُحذَف لا تُترَك stub (درس Kagent، D-173). الأداة نفسها تبقى في
    # سجلّ الأدوات للوكيل المستقبلي — **لكن لا يبلغها مسار الطالب**.

    async def _count_files_in_project(self, extension: str | None = None) -> int | None:
        """يحسب عدد الملفات فعلياً — **بلا عملية فرعية** (M0).

        كان يُنفِّذ أنبوب `find … | wc -l` عبر `execute_shell`، فكان المستهلكَ الحيَّ
        **الوحيد** لمُنفِّذ الأوامر في المونوليث. الدلالة مطابقة رقميّاً (انظر
        `count_project_files`)، والمكسب أمني لا وظيفي: يسقط آخر سبب لبقاء
        `shell=True` على مسارٍ حيّ. `None` عند الفشل — نفس العقد السابق.
        """
        try:
            return await asyncio.to_thread(count_project_files, default_project_root(), extension)
        except OSError:  # قراءة شجرة الملفات قد تفشل (صلاحيات/سباق) — لا نكسر الدور.
            logger.warning("Local file-count walk failed", exc_info=True)
            return None

    async def _build_local_file_count_response(self, question: str) -> str | None:
        """ينشئ رداً محلياً بعد تنفيذ عدّ احترافي حقيقي عبر القدرة الرسمية لذكاء الملفات."""
        recognized, extension = self._file_intelligence_decision(question)
        if not recognized:
            return None

        files_count = await self._count_files_in_project(extension=extension)
        result = make_file_result(extension=extension, count=files_count)
        return result.message

    async def _build_local_retrieval_response(
        self,
        question: str,
        history_messages: list[dict[str, str]] | None = None,
    ) -> str | None:
        """
        ينفذ استرجاعاً محلياً للمعرفة التعليمية عند تعطل service control plane.

        ISS-051 (D-048 — Indexed Knowledge Retrieval):
        المسار المُفضَّل: استخدام matched_entry من knowledge_index.py لجلب ملف
        واحد بالضبط وتنسيقه كبطاقة امتحان نظيفة (بدون YAML، بدون حل).

        المسار البديل: عند فشل المطابقة المُفهرَسة (entry غير موجود في الفهرس)،
        نلجأ إلى wide-net search كما في النسخة القديمة — لكنه نادر الآن
        لأن detect_exercise_retrieval يستخرج matched_entry بنفسه.

        ISS-CONV-C: يقبل history_messages لحل أسئلة المتابعة بالسياق.
        """
        decision = self._exercise_retrieval_full_decision(question, history_messages)
        if not decision.recognized:
            return None

        # المسار المُفضَّل — مطابقة مُفهرَسة دقيقة (الـ 3 المنسَّقة): عرض غني من markdown
        # (نص نظيف + بطاقة امتحان). الفهرس المنسَّق يعمل كـ cache سريع للتمارين الساخنة.
        if decision.matched_entry is not None:
            try:
                raw_content = load_exercise_content(decision.matched_entry)
                if raw_content:
                    return format_exercise_for_display(decision.matched_entry, raw_content)
            except Exception:
                logger.warning("indexed_retrieval_failed", exc_info=True)
            # الملف النصّي مفقود → نص قاعدة البيانات (Supabase = single source of truth)
            db_text = await self._fetch_indexed_entry_db_text(decision.matched_entry)
            if db_text:
                return db_text

        # المسار القابل للتوسّع (مليارات التمارين) — Supabase candidate-generation + rerank
        # يُفعَّل للتمارين غير المُدرَجة في الفهرس المنسَّق. آمن: None عند تعذّر الوصول.
        db_match_text = await self._search_supabase_exercise(question)
        if db_match_text:
            return db_match_text

        # المسار البديل الأخير — wide-net search (legacy)
        try:
            from app.services.chat.tools.retrieval.service import search_educational_content

            result = await search_educational_content(query=question)
            normalized = make_exercise_result(result)
            return normalized.message
        except Exception:
            logger.warning("local_retrieval_fallback_failed", exc_info=True)
            return None

    async def _fetch_indexed_entry_db_text(self, entry: ExerciseEntry) -> str | None:
        """يجلب نص تمرين مُفهرَس من Supabase بهويته (سنة + رقم + موضوع مرجعي).

        يُستخدم كـ single-source-of-truth عند غياب ملف markdown المحلي. None عند
        أي تعذّر وصول → يبقى المسار يعتمد على الفهرس النصّي.
        """
        try:
            from app.services.capabilities.bac_db_retriever import fetch_exercise_raw_text
            from app.services.capabilities.knowledge_index import entry_canonical_ids

            canonical_id = next(iter(entry_canonical_ids(entry)), None)
            raw = await fetch_exercise_raw_text(
                year=entry.year,
                exercise_number=entry.exercise_number,
                canonical_id=canonical_id,
            )
            return self._format_db_exercise_text(raw) if raw else None
        except Exception:
            logger.info("indexed_entry_db_text_failed", exc_info=True)
            return None

    async def _search_supabase_exercise(self, question: str) -> str | None:
        """استرجاع تمرين من Supabase (candidate-gen + rerank) للتمارين غير المُفهرَسة محلياً.

        المسار القابل للتوسّع لمليارات التمارين. None عند تعذّر الوصول/لا نتيجة →
        يتقدّم المسار للبديل (wide-net / المسار العادي).
        """
        try:
            from app.services.capabilities.bac_db_retriever import search_bac_exercises_db

            match = await search_bac_exercises_db(question)
            if match is not None and match.raw_text.strip():
                return self._format_db_exercise_text(match.raw_text)
        except Exception:
            logger.info("supabase_exercise_search_failed", exc_info=True)
        return None

    @staticmethod
    def _format_db_exercise_text(raw_text: str | None) -> str | None:
        """ينظّف نص تمرين قادم من Supabase للعرض (يقطع أي قسم حل تسرَّب، يحذف الفراغ)."""
        if not raw_text or not raw_text.strip():
            return None
        try:
            from app.services.capabilities.exercise_retrieval import _trim_at_solution

            cleaned = _trim_at_solution(raw_text)
        except Exception:
            cleaned = raw_text
        cleaned = (cleaned or "").strip()
        return cleaned or None

    async def _stream_exercise_explanation_response(
        self,
        question: str,
        conversation_id: int | None,
        history_messages: list[dict[str, str]] | None = None,
        precomputed_decision: object = None,  # ExplanationWithContextDecision أو None
    ) -> AsyncGenerator[str, None]:
        """
        يشرح تمرين بكالوريا محدد بالاعتماد على محتواه الكامل من قاعدة المعرفة.

        ISS-053: مسار جديد يحل هلوسة LangGraph عند طلبات "اشرح تمرين الدوال
        العددية 2016". بدلاً من إرسال السؤال بدون سياق، نجلب النص الكامل
        (نص التمرين + الإجابة النموذجية) ونمرره للـ LLM كـ context صريح.

        ISS-058: الآن يستخدم تاريخ المحادثة لربط أسئلة "ماذا نقصد" / "كيف نُثبت"
        بتمرين البكالوريا الذي طُلب حديثاً — فلا يذهب إلى wide-net retrieval.

        ISS-059 (D-053): الآن يقبل `precomputed_decision` لتجنب استدعاء
        `detect_explanation_with_context` مرة ثانية (الـ caller حسبها فعلاً).
        يوفِّر ~10-20ms من زمن TTFB ويتجنَّب file I/O مكرراً.

        يُدرَج في fallback chain بين exercise_retrieval و LangGraph:
          file_intelligence → exercise_retrieval → exercise_explanation → LangGraph → general_chat
        """
        # ISS-059: استخدم القرار المُحسَب مسبقاً إن وُجد (يوفِّر file I/O)
        if precomputed_decision is not None:
            decision = precomputed_decision
        else:
            decision = detect_explanation_with_context(
                ExerciseRetrievalRequest(question=question),
                history_messages=history_messages,
            )
        # D-113 (ISS-115 — وَهْم الإتقان): الشرح السقراطي يستقبل **أسئلة التمرين
        # فقط** (display_content)، لا الإجابة النموذجية (full_content). فلا يملك
        # الـ LLM ما يكشفه. full_content محجوز لوضع التحقق المنفصل حصراً.
        socratic_content = (getattr(decision, "display_content", None) or "").strip()
        if not decision.recognized or not socratic_content:
            return

        try:
            from app.telemetry.path_observer import mark_fallback_used

            mark_fallback_used("exercise_explanation_stream")
        except Exception:
            pass

        try:
            from app.services.chat.local_graph import run_local_graph_with_exercise_context

            async for chunk in run_local_graph_with_exercise_context(
                question=question,
                exercise_full_content=socratic_content,
                conversation_id=conversation_id,
                history_messages=history_messages,
            ):
                if chunk:
                    yield chunk
        except Exception:
            logger.warning("exercise_explanation_stream_failed", exc_info=True)
            return

    async def _stream_local_retrieval_response(
        self,
        question: str,
        history_messages: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        نسخة انسيابية من ``_build_local_retrieval_response`` — تبث المحتوى
        المسترجَع كلمة بكلمة لإنشاء typing-effect بدل dump واحد كبير.

        D-048: المحتوى المُسترجَع ثابت (ليس LLM streaming حقيقي)، لكننا نُقسّمه
        إلى أسطر/فقرات صغيرة ونُغذّيها واحدة تلو الأخرى مع تأخيرات صغيرة
        ليظهر للطالب كأنه يُكتب فوراً أمام عينيه.

        إذا أصدر المولِّد صفر قطعة → fallback chain يتقدم للخطوة التالية.

        ISS-CONV-C: يقبل history_messages لحل أسئلة المتابعة بالسياق.
        """
        full_response = await self._build_local_retrieval_response(question, history_messages)
        if not full_response:
            return

        try:
            from app.telemetry.path_observer import mark_fallback_used

            mark_fallback_used("local_retrieval_stream")
        except Exception:
            pass

        async for chunk in self._stream_markdown_typing(full_response):
            yield chunk

    async def _stream_question_only_response(
        self,
        question: str,
        history_messages: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """ISS-112: «أعطني السؤال رقم N فقط» — اقتطاع حتمي من النص الرسمي.

        الفضيحة المُشخَّصة حياً: طلب «السؤال رقم 2 فقط» كان يُرجع التمرين كاملاً
        أو حلاً مُهلوَساً من LLM. هذا المسار صفر-LLM: يكشف النية + يقتطع السؤال
        المرقَّم من display_content (بدون حل أصلاً) ويبثّه typing-effect.
        يُصدر صفر قطعة عند عدم التعرف → المسار يتابع طبيعياً.
        """
        try:
            from app.services.capabilities.exercise_retrieval import (
                detect_question_only_request,
            )

            decision = detect_question_only_request(
                ExerciseRetrievalRequest(question=question),
                history_messages=history_messages,
            )
        except Exception:
            logger.warning("question_only_detection_failed", exc_info=True)
            return
        if not decision.recognized or not decision.sliced_content:
            return

        logger.info(
            "question_only_preempt reason=%s n=%s file=%s",
            decision.reason,
            decision.question_number,
            getattr(decision.matched_entry, "file_path", None),
        )
        try:
            from app.telemetry.path_observer import mark_fallback_used

            mark_fallback_used("question_only_stream")
        except Exception:
            pass

        async for chunk in self._stream_markdown_typing(decision.sliced_content):
            yield chunk

    async def _build_local_graph_response(
        self,
        question: str,
        conversation_id: int | None,
        history_messages: list[dict[str, str]] | None = None,
    ) -> str | None:
        """
        يشغّل محرك LangGraph المحلي (local_graph.py) ويعيد الرد النهائي.
        يستخدم MemorySaver مع thread_id=conversation_id لاستمرارية السياق.
        يعود None عند أي فشل دون أن يُسقط الـ fallback chain.

        ملاحظة (D-047): هذه نسخة non-streaming — تُستخدم للاختبارات والمسارات
        التي لا تحتاج typing effect. للبث الانسيابي استخدم
        ``_stream_local_graph_response`` (المسار الافتراضي في ``chat_with_agent``).
        """
        try:
            from app.services.chat.local_graph import run_local_graph
            from app.telemetry.path_observer import mark_fallback_used

            mark_fallback_used("local_graph")
            return await run_local_graph(
                question=question,
                conversation_id=conversation_id,
                history_messages=history_messages,
            )
        except Exception:
            logger.warning("local_graph_response_failed", exc_info=True)
            return None

    async def _stream_local_graph_response(
        self,
        question: str,
        conversation_id: int | None,
        history_messages: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        نسخة انسيابية من ``_build_local_graph_response`` — تُصدِر قطع الرد كلمة بكلمة.

        D-047: يكسر "Streaming Event Bottleneck" — بدل buffer-and-wait لـ ainvoke،
        نُغذِّي قناة WS بـ assistant_delta متعدد فوراً من OpenRouter SSE.

        Yields:
            str: قطع المحتوى التتابعية (typically 1-20 chars each).

        إذا أصدر المولِّد صفر قطعة → fallback chain يتقدم للخطوة التالية.
        """
        try:
            from app.services.chat.local_graph import run_local_graph_stream
            from app.telemetry.path_observer import mark_fallback_used

            mark_fallback_used("local_graph_stream")
            async for chunk in run_local_graph_stream(
                question=question,
                conversation_id=conversation_id,
                history_messages=history_messages,
            ):
                if chunk:
                    yield chunk
        except Exception:
            logger.warning("local_graph_stream_failed", exc_info=True)
            return

    async def _build_local_general_chat_response(
        self,
        question: str,
        history_messages: list[dict[str, str]] | None = None,
    ) -> str | None:
        """
        يولد إجابة محلية عامة عبر بوابة الذكاء عند تعطل orchestrator.

        هذا المسار يُستخدم فقط كملاذ أخير بعد فشل مسارات fallback المتخصصة
        (عدّ الملفات والاسترجاع التعليمي)، بهدف إبقاء الدردشة الأساسية متاحة
        في بيئات التطوير مثل Codespaces.
        يحتفظ الآن بسياق المحادثة الكامل لمنع ظاهرة عمى السياق (Context Blindness).
        """
        sanitized_question = question.replace("\x00", "").strip()
        if not sanitized_question:
            return None

        try:
            from app.telemetry.path_observer import mark_fallback_used

            mark_fallback_used("local_general_chat")
        except Exception:  # pragma: no cover — observability never blocks chat
            pass

        local_system_prompt = (
            "أنت مساعد ذكي واسع المعرفة. "
            "أجب بدقة مباشرة على سؤال المستخدم مع الاستناد إلى سياق المحادثة السابقة "
            "عند وجود ضمائر أو إشارات مرجعية. لا تشر إلى تفاصيل داخلية."
        )
        ai_client = get_ai_client()
        try:
            if history_messages:
                history_text = self._format_history_for_prompt(history_messages)
                if history_text:
                    user_message = f"سياق المحادثة السابقة:\n{history_text}\n\nالسؤال الحالي: {sanitized_question}"
                else:
                    user_message = sanitized_question
            else:
                user_message = sanitized_question

            response_text = await ai_client.send_message(local_system_prompt, user_message)
        except Exception:
            logger.warning("local_general_chat_fallback_failed", exc_info=True)
            return None

        clean_response = response_text.replace("\x00", "").strip()
        if not clean_response:
            return None
        return clean_response

    async def _stream_local_general_chat_response(
        self,
        question: str,
        history_messages: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        نسخة انسيابية من ``_build_local_general_chat_response`` — تبث المحتوى
        كلمة بكلمة عبر OpenRouter SSE بدل تجميعه ثم إرساله دفعة واحدة.

        D-047: المسار الأخير في fallback chain — لا يجوز أن يكسر typing effect.
        """
        sanitized_question = question.replace("\x00", "").strip()
        if not sanitized_question:
            return

        try:
            from app.telemetry.path_observer import mark_fallback_used

            mark_fallback_used("local_general_chat_stream")
        except Exception:
            pass

        local_system_prompt = (
            "أنت مساعد ذكي واسع المعرفة. "
            "أجب بدقة مباشرة على سؤال المستخدم مع الاستناد إلى سياق المحادثة السابقة "
            "عند وجود ضمائر أو إشارات مرجعية. لا تشر إلى تفاصيل داخلية."
        )
        ai_client = get_ai_client()

        if history_messages:
            history_text = self._format_history_for_prompt(history_messages)
            user_message = (
                f"سياق المحادثة السابقة:\n{history_text}\n\nالسؤال الحالي: {sanitized_question}"
                if history_text
                else sanitized_question
            )
        else:
            user_message = sanitized_question

        messages: list[dict[str, str]] = [
            {"role": "system", "content": local_system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            async for raw_chunk in ai_client.stream_chat(messages):
                try:
                    choices = raw_chunk.get("choices") if isinstance(raw_chunk, dict) else None
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}) or {}
                    content = delta.get("content")
                    if not content or not isinstance(content, str):
                        continue
                    clean = content.replace("\x00", "")
                    if clean:
                        yield clean
                except Exception:
                    continue
        except Exception:
            logger.warning("local_general_chat_stream_failed", exc_info=True)
            return

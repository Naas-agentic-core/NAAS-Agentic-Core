"""
اختبارات إثبات/نفي تشتت السياق بين مسارات manual agent و LangGraph.

تغطي هذه الاختبارات:
1. _merge_history_with_client_context في الـ monolith (customer_chat / admin)
2. _merge_history_with_client_context في orchestrator context_utils
3. _build_graph_messages_graph vs _build_graph_messages_manual
4. _resolve_thread_id و thread_id stability
5. سلوك checkpointer عند غيابه
6. مسار /agent/chat (manual OrchestratorAgent) مقابل WebSocket LangGraph
"""

import pytest

from app.api.routers.customer_chat import (
    _merge_history_with_client_context as monolith_merge,
)

# ---------------------------------------------------------------------------
# Imports under test — pure functions, no I/O, no DB
# ---------------------------------------------------------------------------
from microservices.orchestrator_service.src.api.context_utils import (
    _extract_client_context_messages,
)
from microservices.orchestrator_service.src.api.context_utils import (
    _merge_history_with_client_context as orchestrator_merge,
)
from microservices.orchestrator_service.src.api.routes import (
    ChatRunContext,
    _build_conversation_thread_id,
    _build_graph_messages_graph,
    _build_graph_messages_manual,
    _conversation_id_from_scoped_thread,
    _resolve_thread_id,
    _safe_thread_id,
)

# ===========================================================================
# SECTION 1 — _merge_history_with_client_context: monolith vs orchestrator
# ===========================================================================

class TestMergeHistoryMonolith:
    """يثبت سلوك دمج التاريخ في الـ monolith (customer_chat / admin)."""

    def test_no_client_context_returns_persisted(self):
        """BUG-PROOF: بدون client_context يُعاد التاريخ المخزّن كاملاً."""
        persisted = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]
        result = monolith_merge(persisted, [])
        assert result == persisted

    def test_empty_persisted_returns_empty_not_client(self):
        """
        BUG CONFIRMED (monolith): إذا كان persisted_history فارغاً يُعاد [] حتى لو
        client_context يحتوي رسائل. هذا يعني أن أول رسالة في محادثة جديدة
        تفقد client_context تماماً.
        """
        client = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]
        result = monolith_merge([], client)
        # الـ monolith يُعيد [] — السياق يُفقد في أول رسالة
        assert result == []

    def test_deduplication_works(self):
        """الرسائل المكررة لا تُضاف مرتين — بعد الـ patch يستخدم overlap detection."""
        persisted = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]
        # client يحتوي persisted كاملاً + رسالة جديدة
        client = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        result = monolith_merge(persisted, client)
        assert result.count({"role": "user", "content": "Q1"}) == 1
        assert {"role": "user", "content": "Q2"} in result

    def test_truncates_to_80_messages(self):
        """يتحقق من أن النتيجة لا تتجاوز 80 رسالة."""
        persisted = [{"role": "user", "content": f"Q{i}"} for i in range(60)]
        client = [{"role": "user", "content": f"C{i}"} for i in range(30)]
        result = monolith_merge(persisted, client)
        assert len(result) <= 80


class TestMergeHistoryOrchestrator:
    """يثبت سلوك دمج التاريخ في orchestrator context_utils."""

    def test_no_client_context_returns_persisted(self):
        persisted = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]
        result = orchestrator_merge(persisted, [])
        assert result == persisted

    def test_empty_persisted_returns_empty(self):
        """
        BUG CONFIRMED (orchestrator): نفس السلوك — persisted فارغ → [] حتى مع client_context.
        """
        client = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]
        result = orchestrator_merge([], client)
        assert result == []

    def test_overlap_detection_appends_only_tail(self):
        """
        يتحقق من أن orchestrator_merge يكتشف التداخل ويضيف فقط الرسائل الجديدة.

        BUG NOTE: الـ overlap detection يعتمد على مطابقة persisted_tail[-3:] كاملاً
        في client. إذا أرسل العميل tail جزئياً فقط (بدون أول رسالة من الـ tail)
        يفشل الكشف ويُعاد persisted فقط بدون الرسائل الجديدة.
        """
        persisted = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        # client يحتوي persisted_tail كاملاً + رسالة جديدة → overlap يُكتشف
        client = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},  # جديدة
        ]
        result = orchestrator_merge(persisted, client)
        assert {"role": "assistant", "content": "A2"} in result
        # لا تكرار
        assert result.count({"role": "user", "content": "Q2"}) == 1

    def test_overlap_detection_fails_with_partial_tail(self):
        """
        BUG CONFIRMED: إذا أرسل العميل tail جزئياً (بدون أول رسالة من persisted_tail)
        يفشل الكشف ويُعاد persisted فقط — الرسائل الجديدة تُفقد.
        """
        persisted = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        # client يبدأ من الرسالة الثانية فقط (partial tail)
        client = [
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},  # جديدة لكن لن تُضاف
        ]
        result = orchestrator_merge(persisted, client)
        # A2 لن تُضاف لأن overlap detection فشل
        assert {"role": "assistant", "content": "A2"} not in result
        assert result == persisted

    def test_no_overlap_returns_persisted_only(self):
        """
        إذا لم يكن هناك تداخل بين persisted و client → يُعاد persisted فقط.
        هذا يمنع تسريب محادثات أخرى.
        """
        persisted = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]
        client = [{"role": "user", "content": "UNRELATED"}, {"role": "assistant", "content": "X"}]
        result = orchestrator_merge(persisted, client)
        assert result == persisted


class TestMergeHistoryDivergence:
    """
    يثبت الفرق الجوهري بين monolith_merge و orchestrator_merge.
    هذا الفرق هو أحد مصادر تشتت السياق.
    """

    def test_both_reject_unrelated_client_messages_after_patch(self):
        """
        بعد الـ patch: كلا الـ implementations يرفضان رسائل client_context
        التي لا تتداخل مع persisted_history — منع تسريب محادثات أخرى.
        """
        persisted = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]
        client = [
            {"role": "user", "content": "UNRELATED_FROM_OTHER_CONV"},
            {"role": "assistant", "content": "LEAKED"},
        ]
        result_monolith = monolith_merge(persisted, client)
        result_orchestrator = orchestrator_merge(persisted, client)

        # كلاهما يرفض الرسائل غير المرتبطة بعد الـ patch
        assert {"role": "user", "content": "UNRELATED_FROM_OTHER_CONV"} not in result_monolith
        assert {"role": "user", "content": "UNRELATED_FROM_OTHER_CONV"} not in result_orchestrator
        # كلاهما يُعيد persisted فقط
        assert result_monolith == persisted
        assert result_orchestrator == persisted


# ===========================================================================
# SECTION 2 — _build_graph_messages_graph vs _build_graph_messages_manual
# ===========================================================================

class TestBuildGraphMessagesGraph:
    """يثبت سلوك بناء رسائل LangGraph graph."""

    def test_no_checkpointer_no_history_returns_only_user_message(self):
        """بدون checkpointer وبدون history → رسالة المستخدم فقط."""
        from langchain_core.messages import HumanMessage
        result = _build_graph_messages_graph(
            objective="ما عاصمة فرنسا؟",
            history_messages=None,
            checkpointer_available=False,
            checkpoint_has_state=False,
        )
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "ما عاصمة فرنسا؟"

    def test_checkpointer_with_state_passes_only_delta(self):
        """
        PROOF: عند وجود checkpointer مع حالة محفوظة → يُمرَّر delta فقط (رسالة واحدة).
        هذا صحيح لأن checkpointer يحمل التاريخ الكامل.
        """
        from langchain_core.messages import HumanMessage
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]
        result = _build_graph_messages_graph(
            objective="Q2",
            history_messages=history,
            checkpointer_available=True,
            checkpoint_has_state=True,
        )
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Q2"

    def test_no_checkpointer_with_history_seeds_full_context(self):
        """
        PROOF: بدون checkpointer مع history → يُمرَّر التاريخ كاملاً + الرسالة الحالية.
        هذا هو مسار استمرارية السياق عند غياب checkpointer.
        """
        from langchain_core.messages import AIMessage, HumanMessage
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]
        result = _build_graph_messages_graph(
            objective="Q2",
            history_messages=history,
            checkpointer_available=False,
            checkpoint_has_state=False,
        )
        assert len(result) == 3
        assert isinstance(result[0], HumanMessage)
        assert isinstance(result[1], AIMessage)
        assert isinstance(result[2], HumanMessage)
        assert result[2].content == "Q2"

    def test_no_duplicate_when_history_ends_with_same_objective(self):
        """لا تكرار إذا كانت آخر رسالة في history هي نفس الـ objective."""
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        result = _build_graph_messages_graph(
            objective="Q2",
            history_messages=history,
            checkpointer_available=False,
            checkpoint_has_state=False,
        )
        user_messages = [m for m in result if hasattr(m, "content") and m.content == "Q2"]
        assert len(user_messages) == 1


class TestBuildGraphMessagesManual:
    """يثبت سلوك بناء رسائل OrchestratorAgent اليدوي."""

    def test_no_history_returns_only_user_message(self):
        result = _build_graph_messages_manual(
            objective="سؤال جديد",
            history_messages=None,
        )
        assert result == [{"role": "user", "content": "سؤال جديد"}]

    def test_with_history_prepends_history(self):
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]
        result = _build_graph_messages_manual(
            objective="Q2",
            history_messages=history,
        )
        assert result[0] == {"role": "user", "content": "Q1"}
        assert result[1] == {"role": "assistant", "content": "A1"}
        assert result[2] == {"role": "user", "content": "Q2"}

    def test_no_duplicate_when_history_ends_with_objective(self):
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        result = _build_graph_messages_manual(
            objective="Q2",
            history_messages=history,
        )
        user_q2 = [m for m in result if m.get("content") == "Q2"]
        assert len(user_q2) == 1

    def test_manual_returns_dicts_not_langchain_objects(self):
        """
        PROOF OF DIVERGENCE: manual يُعيد list[dict] بينما graph يُعيد LangChain messages.
        هذا يعني أن OrchestratorAgent.run() يتلقى format مختلف تماماً.
        """
        result = _build_graph_messages_manual(
            objective="test",
            history_messages=[{"role": "user", "content": "prev"}],
        )
        for msg in result:
            assert isinstance(msg, dict), "manual يجب أن يُعيد dicts"
            assert "role" in msg
            assert "content" in msg


# ===========================================================================
# SECTION 3 — thread_id stability
# ===========================================================================

class TestThreadIdResolution:
    """يثبت ثبات thread_id عبر الطلبات."""

    def test_deterministic_thread_id_from_user_and_conversation(self):
        """نفس user_id + conversation_id → نفس thread_id دائماً."""
        tid1 = _build_conversation_thread_id(42, 100)
        tid2 = _build_conversation_thread_id(42, 100)
        assert tid1 == tid2 == "u42:c100"

    def test_different_users_different_thread_ids(self):
        """مستخدمان مختلفان → thread_ids مختلفة حتى بنفس conversation_id."""
        tid1 = _build_conversation_thread_id(1, 100)
        tid2 = _build_conversation_thread_id(2, 100)
        assert tid1 != tid2

    def test_resolve_thread_id_uses_explicit_if_present(self):
        """إذا كان thread_id موجوداً في context → يُستخدم مباشرة."""
        context: ChatRunContext = {
            "thread_id": "u5:c99",
            "user_id": 5,
            "conversation_id": 99,
        }
        result = _resolve_thread_id(context, fallback_conversation_id=99)
        assert result == "u5:c99"

    def test_resolve_thread_id_builds_from_user_and_conv(self):
        """بدون thread_id صريح → يُبنى من user_id + conversation_id."""
        context: ChatRunContext = {"user_id": 7, "conversation_id": 200}
        result = _resolve_thread_id(context, fallback_conversation_id=200)
        assert result == "u7:c200"

    def test_resolve_thread_id_raises_without_user_id(self):
        """بدون user_id → ValueError لمنع thread_id غير مقيّد."""
        context: ChatRunContext = {"conversation_id": 200}
        with pytest.raises(ValueError, match="user_id required"):
            _resolve_thread_id(context, fallback_conversation_id=200)

    def test_conversation_id_extracted_from_scoped_thread(self):
        """يستخرج conversation_id من thread_id مقيّد بالمستخدم."""
        result = _conversation_id_from_scoped_thread("u42:c100", user_id=42)
        assert result == 100

    def test_scoped_thread_rejects_wrong_user(self):
        """thread_id لمستخدم آخر → None (عزل المستخدمين)."""
        result = _conversation_id_from_scoped_thread("u42:c100", user_id=99)
        assert result is None

    def test_safe_thread_id_rejects_empty_string(self):
        assert _safe_thread_id("") is None
        assert _safe_thread_id("  ") is None

    def test_safe_thread_id_accepts_valid_string(self):
        assert _safe_thread_id("u1:c1") == "u1:c1"

    def test_safe_thread_id_converts_int(self):
        result = _safe_thread_id(42)
        assert result == "42"


# ===========================================================================
# SECTION 4 — context_utils extract
# ===========================================================================

class TestExtractClientContextMessages:
    """يثبت سلوك استخراج client_context_messages."""

    def test_missing_key_returns_empty(self):
        result = _extract_client_context_messages({})
        assert result == []

    def test_non_list_returns_empty(self):
        result = _extract_client_context_messages({"client_context_messages": "not a list"})
        assert result == []

    def test_invalid_role_filtered(self):
        payload = {
            "client_context_messages": [
                {"role": "system", "content": "injected"},
                {"role": "user", "content": "valid"},
            ]
        }
        result = _extract_client_context_messages(payload)
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_truncates_to_50(self):
        payload = {
            "client_context_messages": [
                {"role": "user", "content": f"msg{i}"} for i in range(60)
            ]
        }
        result = _extract_client_context_messages(payload)
        assert len(result) == 50


# ===========================================================================
# SECTION 5 — الفرق الجوهري بين المسارين (proof of divergence)
# ===========================================================================

class TestPathDivergenceProof:
    """
    يثبت بشكل حاسم أن مسار /agent/chat (manual OrchestratorAgent)
    ومسار WebSocket LangGraph يختلفان في:
    1. نوع رسائل الإدخال
    2. وجود/غياب checkpointer
    3. استمرارية السياق عبر الطلبات
    """

    def test_manual_path_has_no_checkpointer_persistence(self):
        """
        PROOF: مسار /agent/chat يستدعي agent.run() مباشرة بدون checkpointer.
        السياق يُحقن يدوياً عبر history_messages فقط.
        إذا لم يُرسل العميل history → السياق يُفقد تماماً.
        """
        # بدون history → رسالة واحدة فقط
        result_no_history = _build_graph_messages_manual(
            objective="ما عاصمة فرنسا؟",
            history_messages=None,
        )
        assert len(result_no_history) == 1

        # مع history → السياق موجود
        history = [
            {"role": "user", "content": "تحدث عن فرنسا"},
            {"role": "assistant", "content": "فرنسا دولة أوروبية..."},
        ]
        result_with_history = _build_graph_messages_manual(
            objective="ما عاصمتها؟",
            history_messages=history,
        )
        assert len(result_with_history) == 3
        # السياق موجود فقط لأن العميل أرسله — لا persistence ذاتية

    def test_langgraph_path_with_checkpointer_needs_only_delta(self):
        """
        PROOF: مسار LangGraph مع checkpointer → delta فقط.
        السياق محفوظ في checkpointer ولا يحتاج إعادة إرسال.
        """
        from langchain_core.messages import HumanMessage
        result = _build_graph_messages_graph(
            objective="ما عاصمتها؟",
            history_messages=[
                {"role": "user", "content": "تحدث عن فرنسا"},
                {"role": "assistant", "content": "فرنسا دولة أوروبية..."},
            ],
            checkpointer_available=True,
            checkpoint_has_state=True,
        )
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

    def test_langgraph_path_without_checkpointer_needs_full_history(self):
        """
        PROOF: مسار LangGraph بدون checkpointer → يحتاج التاريخ الكامل.
        هذا هو نفس سلوك manual — كلاهما يعتمد على history_messages المحقونة.
        """
        history = [
            {"role": "user", "content": "تحدث عن فرنسا"},
            {"role": "assistant", "content": "فرنسا دولة أوروبية..."},
        ]
        result = _build_graph_messages_graph(
            objective="ما عاصمتها؟",
            history_messages=history,
            checkpointer_available=False,
            checkpoint_has_state=False,
        )
        assert len(result) == 3
        assert result[-1].content == "ما عاصمتها؟"

    def test_context_loss_scenario_first_message_new_conversation(self):
        """
        PROOF OF BUG: في أول رسالة لمحادثة جديدة:
        - persisted_history = [] (لا يوجد تاريخ بعد)
        - client_context = [رسائل سابقة من العميل]
        - كلا الـ merge functions تُعيد [] → السياق يُفقد
        """
        client_context = [
            {"role": "user", "content": "تحدث عن فرنسا"},
            {"role": "assistant", "content": "فرنسا دولة أوروبية..."},
        ]
        # كلا الـ implementations تُعيد [] عند persisted = []
        monolith_result = monolith_merge([], client_context)
        orchestrator_result = orchestrator_merge([], client_context)

        assert monolith_result == []
        assert orchestrator_result == []
        # النتيجة: السياق يُفقد في أول رسالة لمحادثة جديدة

    def test_reconnect_same_session_id_not_passed_to_thread(self):
        """
        PROOF: session_id لا يتحول تلقائياً إلى thread_id.
        _resolve_thread_id يبني thread_id من user_id + conversation_id فقط.
        session_id يُستخدم فقط للـ diagnostic logging.
        """
        context_with_session: ChatRunContext = {
            "session_id": "some-session-uuid",
            "user_id": 42,
            "conversation_id": 100,
        }
        thread_id = _resolve_thread_id(context_with_session, fallback_conversation_id=100)
        # thread_id لا يحتوي session_id
        assert "some-session-uuid" not in thread_id
        assert thread_id == "u42:c100"

    def test_switching_conversation_id_changes_thread_id(self):
        """
        PROOF: تغيير conversation_id → thread_id مختلف → checkpointer state مختلف.
        هذا يعني أن تبديل المحادثة يبدأ من الصفر في checkpointer.
        """
        tid1 = _build_conversation_thread_id(42, 100)
        tid2 = _build_conversation_thread_id(42, 200)
        assert tid1 != tid2
        # كل محادثة لها checkpointer state مستقل — هذا صحيح وليس bug


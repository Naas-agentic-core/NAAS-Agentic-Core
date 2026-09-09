"""تجميد سلوك `/agent/chat` قبل تفكيكه — golden master + مصفوفة المسارات.

## لماذا هذا الملفّ موجود

`chat_with_agent_endpoint` تُقاس عند 336 سطراً وتعقيد 51 وعمق تعشيش 13، وهي على وشك
أن تُفكَّك. والقاعدة التي تحكم ذلك (Feathers): **الكود بلا اختبارات هو Legacy**، فشبكة
الأمان تُبنى **قبل** أوّل حركة لا بعدها.

الاختبارات الثلاثة القائمة في `test_agent_chat_contract.py` تغطّي ثلاث حالات من ثلاث
عشرة؛ ولا تلمس: دلالة راية `persisted` (عقد §6.5) · فشل الحفظ · إطار الخطأ · العلامة
`[DB SAVED]` · قمع التكرار في D-047 · المسار الفارغ. هذا الملفّ يغطّي المصفوفة كاملة
ويجمّد **تسلسل الإطارات بالحرف** في `agent_chat_golden.json`.

## لماذا golden master وليس dual-run

البروتوكول الأصلي يقترح إبقاء التنفيذ القديم خلف راية والمقارنة الحيّة. المستودع يمنع
كوداً بلا مستدعٍ حيّ (§6.8 — وKagent حُذف لهذا بالضبط)، فالتجميد هنا على **ملفّ مرجعي
مُلتزَم**: نفس برهان التكافؤ 100٪ بلا كودٍ ميت. وأيّ انحراف يظهر **diff مقروء** في
المراجعة بدل أن يُبتلع.

## القاعدة الحرجة: التصحيح يستهدف موطن المُستدعي (D-168 · القاعدة ١)

`test_agent_chat_contract.py` يُرقّع `routes._ensure_conversation` وأخواتها. حين تنتقل
أجسام المولّدات إلى وحدةٍ شقيقة، تُحَلّ تلك الأسماء من globals الوحدة **الجديدة**،
فيصير الترقيع **لا-عمليةً صامتة** — والاختبار يمسّ قاعدة بيانات حقيقية بدل أن يفشل
بصوتٍ عالٍ. لذلك `_patch_caller` هنا:

1. تُرقّع كلّ وحدةٍ في `CALLER_MODULES` تملك الاسم،
2. و**ترفع** إن لم تجد الاسم في أيّ وحدة.

فالهجرة تصير سطراً واحداً في `CALLER_MODULES`، والهجرة المنسيّة تصير فشلاً صريحاً.
هذا هو الفارق بين شبكة أمانٍ وشبكةٍ بثقبٍ لا يعرفه أحد (D-207 · البند ٥).
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from microservices.orchestrator_service.main import app
from microservices.orchestrator_service.src.api import routes
from tests.microservices.caller_modules import CALLER_MODULES, PATCHED_NAMES, patch_caller

GOLDEN_FILE = Path(__file__).parent / "fixtures" / "agent_chat_golden.json"

# D-168 · قاعدة late-binding: `CALLER_MODULES` و`PATCHED_NAMES` و`patch_caller`
# انتقلت إلى `tests/microservices/caller_modules.py` حين صار ملفّان يحتاجانها
# (ISS-155). الآلية والوثيقة الكاملة هناك — موطنٌ واحد لا نسختان.
_patch_caller = patch_caller


# ─────────────────────────────────────────────────────────────────────────────
# أدوات القيادة
# ─────────────────────────────────────────────────────────────────────────────


def agent_text_event(text: str) -> object:
    """يُنتج ما يُنتجه الوكيل الحقيقي لقطعةٍ نصّية — **بالدالّة نفسها لا بنسخةٍ منها**.

    ISS-156: كان البديل هنا يُنتج نصّاً خاماً (`"مرحبا "`)، بينما
    `OrchestratorAgent._make_json_event` تُنتج إطاراً. فجمّد المرجعُ شكلاً لا يُنتجه
    الوكيل أبداً، ومرّ الترميز المزدوج تحت 1296 اختباراً أخضر حتى شُغِّل المكدّس حيّاً.

    الاستدعاء المباشر للدالّة الحقيقية مقصود: نسخةٌ يدوية هنا كانت ستتفرّق مرّةً
    أخرى بالضبط كما تفرّقت. البديل يتبع عقد الأصل بالبناء لا بالنيّة.
    """
    from microservices.orchestrator_service.src.services.overmind.agents.orchestrator import (
        OrchestratorAgent,
    )

    return OrchestratorAgent._make_json_event(None, text)  # type: ignore[arg-type]


class _FakeAgent:
    """يستبدل `OrchestratorAgent` فيتحكّم الاختبار بأشكال الـchunks الأربعة."""

    def __init__(self, chunks: list[object] | None = None, raises: bool = False) -> None:
        self._chunks = chunks or []
        self._raises = raises
        self.seen: dict[str, object] = {}

    def __call__(self, *args: object, **kwargs: object) -> _FakeAgent:
        return self  # يُستدعى كصنف: OrchestratorAgent(ai_client, tool_registry)

    def run(
        self,
        question: str,
        context: dict[str, object] | None = None,
        history_messages: list | None = None,
    ) -> AsyncGenerator[object, None]:
        self.seen = {
            "question": question,
            "context": context or {},
            "history_messages": history_messages,
        }

        async def _gen() -> AsyncGenerator[object, None]:
            if self._raises:
                raise RuntimeError("agent exploded")
            for chunk in self._chunks:
                yield chunk

        return _gen()


class _FakeAdminApp:
    """يستبدل `app.state.admin_app` ببثّ أحداث LangGraph مُتحكَّم فيه."""

    def __init__(self, events: list[dict[str, object]]) -> None:
        self._events = events
        self.last_inputs: dict[str, object] | None = None
        self.last_config: dict[str, object] | None = None

    async def astream_events(
        self, inputs: dict[str, object], config: dict | None = None, version: str = "v2"
    ) -> AsyncGenerator[dict[str, object], None]:
        self.last_inputs = inputs
        self.last_config = config
        for event in self._events:
            yield event


@pytest.fixture
def preserved_admin_app() -> Iterator[None]:
    """`app` مفردة مشتركة — لا تُترك حالة إدارية تسرّب إلى اختبارٍ تالٍ."""
    sentinel = object()
    previous = getattr(app.state, "admin_app", sentinel)
    yield
    if previous is sentinel:
        if hasattr(app.state, "admin_app"):
            delattr(app.state, "admin_app")
    else:
        app.state.admin_app = previous


@pytest.fixture
def persistence(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, object]]]:
    """يعطّل قاعدة البيانات ويسجّل ما كان سيُكتَب — بلا mock للتفاصيل الداخلية."""
    calls: dict[str, list[dict[str, object]]] = {"ensure": [], "persist": []}

    async def fake_ensure(**kwargs: object) -> tuple[int, list[dict[str, str]]]:
        calls["ensure"].append(kwargs)
        return 4242, []

    async def fake_persist(**kwargs: object) -> None:
        calls["persist"].append(kwargs)

    _patch_caller(monkeypatch, "_ensure_conversation", fake_ensure)
    _patch_caller(monkeypatch, "_persist_assistant_message", fake_persist)
    return calls


def _authenticate(monkeypatch: pytest.MonkeyPatch, *, user_id: int, role: str) -> None:
    def fake_decode(*_args: object, **_kwargs: object) -> tuple[int, dict[str, object]]:
        return user_id, {"role": role}

    _patch_caller(monkeypatch, "_decode_auth_payload_or_401", fake_decode)


def _drive(body: dict[str, object]) -> list[dict[str, object]]:
    """يقود دوراً كاملاً ويعيد الإطارات المُفكَّكة بالترتيب.

    ⚠️ `TestClient(app)` **بلا** `with`: مدير السياق يُشغّل lifespan، وlifespan يبني
    الرسم الحقيقي ويكتبه فوق `app.state.admin_app` — فيُستبدَل البديل الذي ركّبه
    الاختبار، ويحاول الرسم الحقيقي بلوغ postgres على 5432. (رُصد حياً أثناء توليد
    المرجع: `ExecuteToolNode` + `ConnectionRefusedError`.) هذا هو نفس النمط الذي
    تتّبعه `test_agent_chat_contract.py`.
    """
    client = TestClient(app)
    with client.stream(
        "POST", "/agent/chat", headers={"Authorization": "Bearer fake"}, json=body
    ) as response:
        assert response.status_code == 200
        return [json.loads(line) for line in response.iter_lines() if line]


def _normalise(frames: list[dict[str, object]]) -> list[dict[str, object]]:
    """يحيّد اللاحتمي وحده: مُعرّف المتابعة في رسالة الخطأ (uuid4 جديد لكل دور)."""
    out: list[dict[str, object]] = []
    for frame in frames:
        copy = json.loads(json.dumps(frame))
        content = copy.get("payload", {}).get("content")
        if isinstance(content, str) and "رقم المتابعة:" in content:
            copy["payload"]["content"] = content.split("رقم المتابعة:")[0] + "رقم المتابعة: <uuid>"
        out.append(copy)
    return out


def _assert_golden(scenario: str, frames: list[dict[str, object]]) -> None:
    """يقارن بالمرجع المُلتزَم. التحديث فعلٌ صريح يظهر في المراجعة."""
    golden: dict[str, list[dict[str, object]]] = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    assert scenario in golden, (
        f"سيناريو {scenario!r} غير مُجمَّد في {GOLDEN_FILE.name}. "
        f"أضِفه صراحةً — التوليد التلقائي يجعل البوّابة تصادق على أيّ سلوك."
    )
    assert _normalise(frames) == golden[scenario], (
        f"انحراف سلوكي في {scenario!r}.\n   هذا ليس فشلاً تجميلياً: تسلسل الإطارات هو عقد العميل."
    )


# ─────────────────────────────────────────────────────────────────────────────
# مسار الزبون
# ─────────────────────────────────────────────────────────────────────────────

CUSTOMER_BODY: dict[str, object] = {"question": "ما هو الاحتمال؟", "user_id": 7, "context": {}}


def test_customer_string_chunks_stream_persist_and_finalise(
    monkeypatch: pytest.MonkeyPatch, persistence: dict[str, list[dict[str, object]]]
) -> None:
    """أبسط مسار حيّ: قطع الوكيل الحقيقية ⇒ deltas + حفظ + إطار نهائي واحد."""
    _authenticate(monkeypatch, user_id=7, role="customer")
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(
        monkeypatch,
        "OrchestratorAgent",
        _FakeAgent([agent_text_event("مرحبا "), agent_text_event("بك")]),
    )

    frames = _drive(CUSTOMER_BODY)

    _assert_golden("customer_string_chunks", frames)
    assert len(persistence["persist"]) == 1
    assert persistence["persist"][0]["content"] == "مرحبا بك"
    assert persistence["persist"][0]["chat_scope"] == "customer"


def test_no_frame_is_encoded_twice_and_no_envelope_is_persisted(
    monkeypatch: pytest.MonkeyPatch, persistence: dict[str, list[dict[str, object]]]
) -> None:
    """ISS-156 — الإطار يُرمَّز مرّةً واحدة، والمحفوظ نصُّ الطالب لا المظروف.

    مُثبَت حيّاً قبل الإصلاح على مكدّسٍ كامل بـPostgres حقيقي: **32 إطاراً من 34**
    كانت تحمل إطاراً مُسلسَلاً داخل `payload.content`، والصفّ المحفوظ في
    `customer_messages` كان حرفياً `{"type": "assistant_delta", ...}`.

    السبب: `_make_json_event` تُنتج إطاراً جاهزاً، وفرع `str` كان يلفّه ثانيةً عبر
    `_serialize_stream_frame`. والمُراكِم كان يجمع المظروف فيتسمّم الصفّ المحفوظ.
    """
    _authenticate(monkeypatch, user_id=7, role="customer")
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(
        monkeypatch,
        "OrchestratorAgent",
        _FakeAgent([agent_text_event("الاحتمال "), agent_text_event("هو النسبة.")]),
    )

    frames = _drive(CUSTOMER_BODY)

    for frame in frames:
        content = frame.get("payload", {}).get("content")
        if not isinstance(content, str) or not content.lstrip().startswith("{"):
            continue
        try:
            inner = json.loads(content)
        except json.JSONDecodeError:
            continue
        raise AssertionError(
            f"إطارٌ مُرمَّز مرّتين: `payload.content` يحمل إطاراً كاملاً {inner!r}.\n"
            f"   الطالب يرى JSON خاماً بدل جوابه."
        )

    assert persistence["persist"][0]["content"] == "الاحتمال هو النسبة.", (
        "المحفوظ ليس نصّ الطالب — تسمّم `customer_messages` بمظروف JSON (ISS-156)."
    )


def test_customer_dict_delta_and_final_chunks(
    monkeypatch: pytest.MonkeyPatch, persistence: dict[str, list[dict[str, object]]]
) -> None:
    """شكلا الـdict: `assistant_delta` يُبَثّ، و`assistant_final` يُلتقط ولا يُبَثّ خاماً."""
    _authenticate(monkeypatch, user_id=7, role="customer")
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(
        monkeypatch,
        "OrchestratorAgent",
        _FakeAgent(
            [
                {"type": "assistant_delta", "payload": {"content": "جزء"}},
                {"type": "assistant_final", "payload": {"content": "-تمام"}},
            ]
        ),
    )

    frames = _drive(CUSTOMER_BODY)

    _assert_golden("customer_dict_chunks", frames)
    assert persistence["persist"][0]["content"] == "جزء-تمام"


def test_customer_empty_response_persists_nothing_and_emits_no_terminal_frame(
    monkeypatch: pytest.MonkeyPatch, persistence: dict[str, list[dict[str, object]]]
) -> None:
    """المسار الفارغ: لا حفظ ولا إطار نهائي — سلوكٌ قائم يُجمَّد كما هو."""
    _authenticate(monkeypatch, user_id=7, role="customer")
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(monkeypatch, "OrchestratorAgent", _FakeAgent([]))

    frames = _drive(CUSTOMER_BODY)

    _assert_golden("customer_empty", frames)
    assert persistence["persist"] == []


def test_customer_persistence_failure_still_ends_with_one_terminal_frame(
    monkeypatch: pytest.MonkeyPatch, persistence: dict[str, list[dict[str, object]]]
) -> None:
    """فشل الحفظ لا يُسكِت الدور: خطأ ثمّ إطار نهائي (§6.5 — لا فشل صامت)."""
    _authenticate(monkeypatch, user_id=7, role="customer")
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(monkeypatch, "OrchestratorAgent", _FakeAgent(["نص"]))

    async def boom(**_kwargs: object) -> None:
        raise RuntimeError("db down")

    _patch_caller(monkeypatch, "_persist_assistant_message", boom)

    frames = _drive(CUSTOMER_BODY)

    _assert_golden("customer_persist_failure", frames)
    assert [frame["type"] for frame in frames].count("assistant_final") == 1


def test_customer_agent_failure_emits_a_single_safe_error(
    monkeypatch: pytest.MonkeyPatch, persistence: dict[str, list[dict[str, object]]]
) -> None:
    """انفجار الوكيل ⇒ إطار خطأ واحد آمن، بلا تسريب تشخيصي."""
    _authenticate(monkeypatch, user_id=7, role="customer")
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(monkeypatch, "OrchestratorAgent", _FakeAgent(raises=True))

    frames = _drive(CUSTOMER_BODY)

    _assert_golden("customer_agent_failure", frames)
    assert "agent exploded" not in json.dumps(frames, ensure_ascii=False)


def test_compatibility_facade_delegates_the_user_message_to_the_monolith(
    monkeypatch: pytest.MonkeyPatch, persistence: dict[str, list[dict[str, object]]]
) -> None:
    """مصافحة §6.5: الواجهة التوافقية ⇒ `skip_user_message=True` — كاتبٌ واحد."""
    _authenticate(monkeypatch, user_id=7, role="customer")
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(monkeypatch, "OrchestratorAgent", _FakeAgent(["نص"]))

    _drive({**CUSTOMER_BODY, "context": {"compatibility_facade": True}})

    assert persistence["ensure"][0]["skip_user_message"] is True


def test_without_the_facade_the_orchestrator_writes_the_user_message(
    monkeypatch: pytest.MonkeyPatch, persistence: dict[str, list[dict[str, object]]]
) -> None:
    """الطرف المقابل للمصافحة — وإلّا مرّ العقد بنصفه."""
    _authenticate(monkeypatch, user_id=7, role="customer")
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(monkeypatch, "OrchestratorAgent", _FakeAgent(["نص"]))

    _drive(CUSTOMER_BODY)

    assert persistence["ensure"][0]["skip_user_message"] is False


def test_jwt_identity_overrides_a_forged_body_user_id(
    monkeypatch: pytest.MonkeyPatch, persistence: dict[str, list[dict[str, object]]]
) -> None:
    """أمنيّ: هوية الـJWT تتفوّق على `user_id` في الجسم — لا انتحال."""
    _authenticate(monkeypatch, user_id=7, role="customer")
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(monkeypatch, "OrchestratorAgent", _FakeAgent(["نص"]))

    _drive({**CUSTOMER_BODY, "user_id": 99999})

    assert persistence["ensure"][0]["user_id"] == 7


# ─────────────────────────────────────────────────────────────────────────────
# مسار الإدارة
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_BODY: dict[str, object] = {
    "question": "count python files",
    "user_id": 11,
    "context": {"chat_scope": "admin"},
}

_ADMIN_FINAL_EVENT: dict[str, object] = {
    "event": "on_chain_end",
    "name": "LangGraph",
    "data": {"output": {"final_response": "أربعة ملفات"}},
}


def test_admin_without_token_streaming_carries_the_full_text(
    monkeypatch: pytest.MonkeyPatch,
    persistence: dict[str, list[dict[str, object]]],
    preserved_admin_app: None,
) -> None:
    """بلا بثٍّ رمزي ⇒ الإطار النهائي يحمل النصّ كاملاً."""
    _authenticate(monkeypatch, user_id=11, role="admin")
    app.state.admin_app = _FakeAdminApp([_ADMIN_FINAL_EVENT])

    frames = _drive(ADMIN_BODY)

    _assert_golden("admin_no_token_stream", frames)
    assert persistence["persist"][0]["chat_scope"] == "admin"


def test_admin_token_streaming_suppresses_the_duplicate_final_payload(
    monkeypatch: pytest.MonkeyPatch,
    persistence: dict[str, list[dict[str, object]]],
    preserved_admin_app: None,
) -> None:
    """D-047: بعد بثّ القطع، الإطار النهائي يحمل `""` — المتصفّح يجمعها بنفسه."""
    _authenticate(monkeypatch, user_id=11, role="admin")

    class _Chunk:
        content = "جزء"

    app.state.admin_app = _FakeAdminApp(
        [
            {"event": "on_chain_start", "name": "planner", "data": {}},
            {"event": "on_chat_model_stream", "data": {"chunk": _Chunk()}},
            {"event": "on_chain_end", "name": "planner", "data": {"output": {}}},
            _ADMIN_FINAL_EVENT,
        ]
    )

    frames = _drive(ADMIN_BODY)

    _assert_golden("admin_token_stream", frames)
    finals = [frame for frame in frames if frame["type"] == "assistant_final"]
    assert finals[0]["payload"]["content"] == ""


def test_admin_custom_event_streaming_is_forwarded(
    monkeypatch: pytest.MonkeyPatch,
    persistence: dict[str, list[dict[str, object]]],
    preserved_admin_app: None,
) -> None:
    """D-048: بثّ من عُقَد DSPy/OpenAI الخام عبر `on_custom_event`."""
    _authenticate(monkeypatch, user_id=11, role="admin")
    app.state.admin_app = _FakeAdminApp(
        [
            {
                "event": "on_custom_event",
                "data": {"chunk_type": "assistant_delta", "content": "مخصّص"},
            },
            _ADMIN_FINAL_EVENT,
        ]
    )

    frames = _drive(ADMIN_BODY)

    _assert_golden("admin_custom_event", frames)


def test_admin_never_leaks_the_json_envelope_to_the_client(
    monkeypatch: pytest.MonkeyPatch,
    persistence: dict[str, list[dict[str, object]]],
    preserved_admin_app: None,
) -> None:
    """ISS-056 (D-049): `final_response` قد يصل **مظروفاً** لا نصّاً.

    `SynthesizerNode` يُرجِع dict بحقول (`المصدر` · `مستوى_الثقة` · `التمرين` …)؛
    وتسليمه خاماً هو الكارثة التي وُجدت `_extract_human_readable_response` لمنعها.
    كلّ سيناريوهات الإدارة الأخرى هنا تُغذّي نصّاً بسيطاً، فيتساوى المُستخرِج مع
    `str()` ولا يُختبَر شيء — وهي فجوةٌ **كشفها اختبار الطفرات** لا التخطيط:
    طفرةُ استبدال المُستخرِج بـ`str()` نجت حيّةً.
    """
    _authenticate(monkeypatch, user_id=11, role="admin")
    app.state.admin_app = _FakeAdminApp(
        [
            {
                "event": "on_chain_end",
                "name": "LangGraph",
                "data": {
                    "output": {
                        "final_response": {
                            "المصدر": "معرفة مادة",
                            "مستوى_الثقة": 0.91,
                            "التمرين": "الجواب البشري الوحيد",
                            "السنة": 2024,
                        }
                    }
                },
            }
        ]
    )

    frames = _drive(ADMIN_BODY)

    final = next(frame for frame in frames if frame["type"] == "assistant_final")
    assert final["payload"]["content"] == "الجواب البشري الوحيد"
    wire = json.dumps(frames, ensure_ascii=False)
    for envelope_key in ("المصدر", "مستوى_الثقة", "السنة"):
        assert envelope_key not in wire, f"تسرّب مفتاح المظروف {envelope_key} إلى العميل"
    assert persistence["persist"][0]["content"] == "الجواب البشري الوحيد"


def test_admin_without_a_graph_emits_a_single_safe_error(
    monkeypatch: pytest.MonkeyPatch,
    persistence: dict[str, list[dict[str, object]]],
    preserved_admin_app: None,
) -> None:
    """غياب `admin_app` ⇒ خطأ صريح واحد، لا تعليق ولا صمت."""
    _authenticate(monkeypatch, user_id=11, role="admin")
    if hasattr(app.state, "admin_app"):
        delattr(app.state, "admin_app")

    frames = _drive(ADMIN_BODY)

    _assert_golden("admin_missing_graph", frames)


def test_admin_persistence_failure_still_ends_with_one_terminal_frame(
    monkeypatch: pytest.MonkeyPatch,
    persistence: dict[str, list[dict[str, object]]],
    preserved_admin_app: None,
) -> None:
    """فشل الحفظ في المسار الإداري ⇒ خطأ ثمّ إطار نهائي (§6.5)."""
    _authenticate(monkeypatch, user_id=11, role="admin")
    app.state.admin_app = _FakeAdminApp([_ADMIN_FINAL_EVENT])

    async def boom(**_kwargs: object) -> None:
        raise RuntimeError("db down")

    _patch_caller(monkeypatch, "_persist_assistant_message", boom)

    frames = _drive(ADMIN_BODY)

    _assert_golden("admin_persist_failure", frames)
    assert [frame["type"] for frame in frames].count("assistant_final") == 1


def test_a_non_admin_jwt_cannot_reach_the_admin_graph(
    monkeypatch: pytest.MonkeyPatch,
    persistence: dict[str, list[dict[str, object]]],
    preserved_admin_app: None,
) -> None:
    """fail-closed: `chat_scope=admin` في الجسم لا يمنح سلطة — الـJWT وحده يقرّر."""
    _authenticate(monkeypatch, user_id=12, role="customer")
    fake_admin = _FakeAdminApp([_ADMIN_FINAL_EVENT])
    app.state.admin_app = fake_admin
    _patch_caller(monkeypatch, "get_ai_client", lambda: object())
    _patch_caller(monkeypatch, "OrchestratorAgent", _FakeAgent(["مسار الزبون"]))

    _drive(ADMIN_BODY)

    assert fake_admin.last_inputs is None, "الرسم الإداري نُفِّذ لهوية غير إدارية"
    assert persistence["persist"][0]["chat_scope"] == "customer"


# ─────────────────────────────────────────────────────────────────────────────
# العقود البنيوية
# ─────────────────────────────────────────────────────────────────────────────


def test_every_scenario_ends_with_exactly_one_terminal_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§6.5: إطار نهائي **واحد** لكل دور — يُقرأ من المرجع المُجمَّد نفسه."""
    golden: dict[str, list[dict[str, object]]] = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    for scenario, frames in golden.items():
        terminal = [
            frame for frame in frames if frame["type"] in {"assistant_final", "assistant_error"}
        ]
        if scenario == "customer_empty":
            assert terminal == [], "المسار الفارغ لا يُنهي — سلوكٌ قائم مُجمَّد"
            continue
        finals = [frame for frame in terminal if frame["type"] == "assistant_final"]
        assert len(finals) <= 1, f"{scenario}: أكثر من إطار نهائي واحد"
        assert terminal, f"{scenario}: دورٌ بلا إطار نهائي — فشلٌ صامت"


def test_caller_modules_covers_every_module_that_calls_a_patched_name() -> None:
    """يسدّ الثقب المتبقّي في `_patch_caller` — بنيويّاً لا بالثقة.

    `_patch_caller` ترفع حين **لا وحدة** تملك الاسم. لكنّ `routes` يُعيد تصدير
    المنقولات (`noqa: F401`)، فلو انتقل مُستدعٍ إلى وحدةٍ جديدة نُسي إدراجها،
    لوجدت الدالّةُ الاسمَ في `routes` ورقّعته هناك و**نجحت صامتةً** بينما المُستدعي
    الحقيقي بلا ترقيع.

    فالمِلكية تُقاس على شجرة الصياغة: كلّ وحدة في الحزمة **تستدعي** اسماً مُرقَّعاً
    يجب أن تكون في `CALLER_MODULES`. (D-208 · البند ٦: `parse_source` ترفع بدل أن
    تشهد بنظافة ملفٍّ لم تُقرأ.)
    """
    import ast
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "fitness"))
    from _ast_util import parse_source

    api_dir = Path(routes.__file__).parent
    listed = {Path(module.__file__).name for module in CALLER_MODULES}

    missing: list[str] = []
    for path in sorted(api_dir.glob("*.py")):
        tree = parse_source(path)
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        hits = called & set(PATCHED_NAMES)
        if hits and path.name not in listed:
            missing.append(f"{path.name} تستدعي {sorted(hits)}")

    assert not missing, (
        "وحداتٌ تستدعي أسماءً مُرقَّعة وهي خارج CALLER_MODULES:\n  "
        + "\n  ".join(missing)
        + "\n   الترقيع سيجدها في إعادة تصدير `routes` وينجح صامتاً بينما المُستدعي "
        "الحقيقي يمسّ قاعدة بيانات حقيقية (D-168 · قاعدة late-binding)."
    )


def test_the_late_binding_guard_raises_instead_of_patching_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """تجربة سلبية للآلية التي تحمي التفكيك كلّه — حارسٌ لا يُثبَت أنه يصرخ ليس حارساً.

    لو انتقل مُستدعٍ إلى وحدةٍ جديدة ولم تُضَف إلى `CALLER_MODULES`، فالترقيع يصير
    لا-عمليةً صامتة والاختبار يمسّ قاعدة بيانات حقيقية بدل أن يفشل. هنا نُثبت أن
    الحارس يرفع بدل أن يمرّ.
    """
    with pytest.raises(AssertionError, match="CALLER_MODULES"):
        _patch_caller(monkeypatch, "_a_caller_that_moved_away", object())


def test_the_persisted_flag_is_stripped_before_it_reaches_the_wire() -> None:
    """يوثّق عطباً حيّاً بدل أن يزعم صحّةً (ISS-153 — لا يُصلَح في هذه الجولة).

    الشيفرة تضع `persisted: True` على الإطار النهائي (routes.py:1097 · :1218)، لكن
    `StreamFrame` تعلن `type` و`payload` فقط، فيسقط المفتاح عند `model_dump()`.
    وبغيابه يقرأ المونوليث «لم يُحفَظ» (§6.5: غياب الإشارة = فشل) فيكتب احتياطياً
    فوق كتابةٍ تمّت — وهي **الكتابة المزدوجة** التي وُجد §6.5 ليمنعها.

    هذا الاختبار يُجمّد الواقع لا الأمنية: حين يُصلَح العطب **يفشل**، وهو المطلوب —
    عندها يُقلَب مع تحديث المرجع في نفس الـPR.
    """
    from microservices.orchestrator_service.src.api.stream_serialization import (
        _serialize_stream_frame_sync,
    )

    wire = _serialize_stream_frame_sync(
        {"type": "assistant_final", "payload": {"content": "x"}, "persisted": True}
    )

    assert "persisted" not in wire
    assert json.loads(wire) == {"type": "assistant_final", "payload": {"content": "x"}}

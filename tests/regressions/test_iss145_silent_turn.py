"""ISS-145 — الإرفاق ليس تسليماً (D-230).

**البلاغ أُغلق على المعيار الخطأ.** الإغلاق ادّعى `truly_silent = 0` لأنه فحص أنّ
مكوّناً **مُرفَق** بالصفّ، لا أنه **قابل للرسم**. والفحص الصحيح على قاعدة الإنتاج
(2026-08-08) يقول:

    صفوف بمحتوى فارغ            212
    منها بلا ui_component          0
    منها بمكوّنٍ لا تعرفه الواجهة  7   ← أدوارٌ صامتة فعلاً
    منها مُصيَّرة فعلاً           205

السبعةُ كلّها `worked_example_card` — الاسم الذي **حظره D-115** (المثال المكشوف يخرق
القاعدة الذهبية D-113). فرأى الطالب «تعذّر عرض المكوّن التفاعلي» ولا شيء غيره.

هذه الاختبارات تُثبت أن الصفّ الصامت **لم يعد يُكتب**.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from app.api.routers.customer_chat_support.pedagogy import _persist_ui_component_cards
from app.contracts.streaming import KNOWN_UI_COMPONENTS

#: الحمولة الحقيقية من الإنتاج (المحادثة 763 · 2026-06-15).
ISS_145_CARD: dict[str, Any] = {
    "component": "worked_example_card",
    "props": {"concept_id": "probability", "title": "مثال محلول كامل"},
    "fallback_text": "مثال محلول",
}

RENDERABLE_CARD: dict[str, Any] = {
    "component": "probability_tree",
    "props": {"nodes": []},
    "fallback_text": "شجرة الاحتمالات",
}


class _SpyService:
    """يلتقط كل نداء حفظ — لا قاعدة بيانات، فالسلوك المُختبَر هو القرار لا التخزين."""

    instances: ClassVar[list[_SpyService]] = []

    def __init__(self, _db: object) -> None:
        self.saved: list[dict[str, Any]] = []
        _SpyService.instances.append(self)

    async def save_message(self, **kwargs: Any) -> None:
        self.saved.append(kwargs)


class _NullSession:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_: object) -> bool:
        return False


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> type[_SpyService]:
    """D-168 (late-binding): نُرقِّع الوحدة التي **يعيش فيها المستدعي**."""
    module = "app.api.routers.customer_chat_support.pedagogy"
    _SpyService.instances = []
    monkeypatch.setattr(f"{module}.CustomerChatBoundaryService", _SpyService)
    monkeypatch.setattr(f"{module}.async_session_factory", lambda: _NullSession())
    return _SpyService


class TestUnrenderableCardIsNeverPersisted:
    async def test_the_seven_silent_turns_cannot_recur(self, spy) -> None:
        """الحمولة الحقيقية التي أنتجت ٧ أدوارٍ صامتة — لا تُكتب بعد اليوم."""
        await _persist_ui_component_cards(conversation_id=763, cards=[ISS_145_CARD])
        assert spy.instances == [], "لا جلسة تُفتَح أصلاً حين لا شيء يستحقّ الحفظ"

    async def test_unknown_component_is_dropped_and_logged(
        self, spy, caplog: pytest.LogCaptureFixture
    ) -> None:
        """يُسجَّل كي يُشخَّص، ولا يُخزَّن كي لا يَصمت."""
        with caplog.at_level("WARNING"):
            await _persist_ui_component_cards(
                conversation_id=1, cards=[{"component": "invented_card", "props": {}}]
            )
        assert "ui_component_card_dropped_unrenderable" in caplog.text

    async def test_renderable_card_is_still_persisted(self, spy) -> None:
        """⚠️ الإصلاح لا يجوز أن يُسكِت البطاقات السليمة (ISS-106 يبقى قائماً)."""
        await _persist_ui_component_cards(conversation_id=7, cards=[RENDERABLE_CARD])
        assert len(spy.instances) == 1
        saved = spy.instances[0].saved
        assert len(saved) == 1
        assert saved[0]["ui_component"] == RENDERABLE_CARD
        assert saved[0]["content"] == ""

    async def test_mixed_batch_keeps_only_the_renderable(self, spy) -> None:
        await _persist_ui_component_cards(conversation_id=9, cards=[ISS_145_CARD, RENDERABLE_CARD])
        saved = spy.instances[0].saved
        assert [s["ui_component"]["component"] for s in saved] == ["probability_tree"]

    @pytest.mark.parametrize("junk", [None, {}, {"component": ""}, {"component": 5}, 42])
    async def test_malformed_cards_are_dropped(self, spy, junk: object) -> None:
        await _persist_ui_component_cards(conversation_id=2, cards=[junk])  # type: ignore[list-item]
        assert spy.instances == []


class TestTheBannedNameStaysBanned:
    def test_worked_example_card_is_not_renderable(self) -> None:
        """D-115 عكسَ الكشف: المثال المكشوف يخرق القاعدة الذهبية (D-113)."""
        assert "worked_example_card" not in KNOWN_UI_COMPONENTS

    def test_every_persisted_name_must_be_declared(self) -> None:
        """المصدر الوحيد لـ«قابل للرسم» هو العقد — لا قائمةٌ ثانية في مسار الحفظ."""
        assert ISS_145_CARD["component"] not in KNOWN_UI_COMPONENTS
        assert RENDERABLE_CARD["component"] in KNOWN_UI_COMPONENTS

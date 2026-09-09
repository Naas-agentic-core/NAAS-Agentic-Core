"""اختبارات طبقة الرسائل في المونوليث — D-201.

تُثبِت ثلاثة أشياء: أنّ اختيار السائق صادق (بلا عنوان ⇒ ذاكرة)، وأنّ النشر **لا يكسر
دور طالب أبداً**، وأنّ المستهلك يُنتِج أثراً حقيقياً — لا ناشرٌ في الفراغ.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.messaging import consumers
from app.services.messaging.runtime import (
    build_envelope,
    get_event_publisher,
    publish_event,
    reset_event_publisher,
)
from shared.messaging import EventEnvelope, EventPublisher, InMemoryEventBus, Topic
from shared.messaging.notification_rules import NOTIFICATION_RULES, derive_notification


@pytest.fixture(autouse=True)
def _clean_messaging_state():
    reset_event_publisher()
    consumers.reset_subscribers()
    consumers.reset_ledger()
    yield
    reset_event_publisher()
    consumers.reset_subscribers()
    consumers.reset_ledger()


# ── اختيار السائق ───────────────────────────────────────────────────────────────


def test_without_a_broker_address_the_in_memory_driver_is_selected() -> None:
    """
    السائق في الذاكرة **افتراضٌ حيّ لا نموذج أوّلي**: مسار الأحداث يبقى عاملاً بلا
    بنية تحتية، فلا تُعلَّق قدرةٌ على وسيطٍ غائب (§6.6).
    """
    assert isinstance(get_event_publisher(), InMemoryEventBus)


def test_the_publisher_is_a_singleton_per_process() -> None:
    """ناشرٌ يتبدّل تحت حِمل يوزّع الأحداث على وسيطين بلا ترتيبٍ بينهما."""
    assert get_event_publisher() is get_event_publisher()


def test_an_unreachable_broker_falls_back_loudly(monkeypatch, caplog) -> None:
    """
    عنوانٌ مضبوط ووسيطٌ متعذّر عطبٌ تشغيلي يجب أن يُرى — لا أن يمرّ كأنّ شيئاً لم يكن.
    """
    from app.core import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "broker:9092", raising=False)

    def _explode(*_args, **_kwargs) -> None:
        raise RuntimeError("no driver")

    monkeypatch.setattr(
        "app.services.messaging.kafka_publisher.KafkaEventPublisher.__init__", _explode
    )

    with caplog.at_level("ERROR"):
        publisher = get_event_publisher()

    assert isinstance(publisher, InMemoryEventBus)
    assert "kafka_publisher_unavailable" in caplog.text


# ── بناء الظرف ──────────────────────────────────────────────────────────────────


def test_an_envelope_carries_the_ambient_correlation_id() -> None:
    """المُعرَّف **يُمَدّ ولا يُخترَع** (D-189) — الاختراع يقطع السلسلة بدل مدّها."""
    from app.core.logging import correlation_id

    token = correlation_id.set("turn-42")
    try:
        envelope = build_envelope(
            topic=Topic.PRODUCT_EVENTS, event_name="chat_turn_started", payload={}
        )
    finally:
        correlation_id.reset(token)

    assert envelope.correlation_id == "turn-42"


def test_each_built_envelope_gets_its_own_identity() -> None:
    first = build_envelope(topic=Topic.PRODUCT_EVENTS, event_name="a", payload={})
    second = build_envelope(topic=Topic.PRODUCT_EVENTS, event_name="a", payload={})
    assert first.event_id != second.event_id


# ── النشر لا يكسر دوراً ─────────────────────────────────────────────────────────


async def test_publishing_succeeds_on_the_default_driver() -> None:
    envelope = build_envelope(
        topic=Topic.PRODUCT_EVENTS, event_name="chat_turn_started", payload={"user_id": 3}
    )
    assert await publish_event(envelope) is True


async def test_a_failing_publisher_never_raises_into_the_turn(monkeypatch, caplog) -> None:
    """
    حدثٌ ضائع خسارةُ قياس؛ دورٌ ساقط خسارةُ طالب. الابتلاع مسموحٌ **هنا وحدها**.
    """

    class BrokenPublisher(EventPublisher):
        async def publish(self, envelope: EventEnvelope) -> None:
            raise RuntimeError("broker down")

    monkeypatch.setattr(
        "app.services.messaging.runtime._build_publisher", lambda: BrokenPublisher()
    )
    reset_event_publisher()

    with caplog.at_level("WARNING"):
        published = await publish_event(
            build_envelope(topic=Topic.PRODUCT_EVENTS, event_name="x", payload={})
        )

    assert published is False
    assert "event_publish_failed" in caplog.text


# ── قواعد الإشعار ───────────────────────────────────────────────────────────────


def test_an_event_without_a_rule_stays_silent() -> None:
    """الافتراض هو الصمت. الصمت قابل للإصلاح؛ الإزعاج الافتراضي يُفقِد المستخدم."""
    assert derive_notification("chat_turn_started", {"user_id": 1}) is None


def test_the_guardian_rule_produces_a_request_for_the_student() -> None:
    request = derive_notification("guardian_link_accepted", {"user_id": 12})
    assert request is not None
    assert request.template == "guardian_linked"
    assert request.user_id == 12


@pytest.mark.parametrize("raw", [None, "abc", {"nested": 1}])
def test_a_missing_or_unusable_user_id_yields_none_rather_than_a_guess(raw) -> None:
    request = derive_notification("guardian_link_accepted", {"user_id": raw})
    assert request is not None
    assert request.user_id is None


def test_a_string_user_id_is_accepted() -> None:
    assert derive_notification("guardian_link_accepted", {"user_id": "7"}).user_id == 7


def test_every_rule_names_a_template_and_a_channel() -> None:
    for template, channel in NOTIFICATION_RULES.values():
        assert template
        assert channel


# ── المستهلك ────────────────────────────────────────────────────────────────────


async def test_the_consumer_delivers_to_every_registered_subscriber() -> None:
    seen: list[str] = []

    async def subscriber(envelope: EventEnvelope) -> None:
        seen.append(envelope.event_name)

    consumers.subscribe(Topic.PRODUCT_EVENTS, subscriber)
    bus = InMemoryEventBus()
    await bus.publish(
        build_envelope(topic=Topic.PRODUCT_EVENTS, event_name="chat_turn_started", payload={})
    )

    outcomes = await consumers.drain(bus, Topic.PRODUCT_EVENTS)
    assert [outcome.handled for outcome in outcomes] == [True]
    assert seen == ["chat_turn_started"]


async def test_a_redelivered_event_is_not_processed_twice() -> None:
    calls: list[str] = []

    async def subscriber(envelope: EventEnvelope) -> None:
        calls.append(envelope.event_id)

    consumers.subscribe(Topic.PRODUCT_EVENTS, subscriber)
    bus = InMemoryEventBus()
    envelope = build_envelope(topic=Topic.PRODUCT_EVENTS, event_name="a", payload={})

    await bus.publish(envelope)
    await consumers.drain(bus, Topic.PRODUCT_EVENTS)
    await bus.publish(envelope)
    outcomes = await consumers.drain(bus, Topic.PRODUCT_EVENTS)

    assert outcomes[0].duplicate is True
    assert calls == [envelope.event_id]


async def test_a_failing_subscriber_sends_the_envelope_down_the_failure_path() -> None:
    async def subscriber(_: EventEnvelope) -> None:
        raise TimeoutError("db down")

    consumers.subscribe(Topic.PRODUCT_EVENTS, subscriber)
    bus = InMemoryEventBus()
    await bus.publish(build_envelope(topic=Topic.PRODUCT_EVENTS, event_name="a", payload={}))

    outcomes = await consumers.drain(bus, Topic.PRODUCT_EVENTS)
    assert outcomes[0].handled is False
    assert outcomes[0].disposition is not None


async def test_the_dead_letter_topic_is_never_drained_automatically() -> None:
    """
    إعادة تشغيل DLQ آلياً تُعيد نفس الرسالة المسمومة إلى نفس المستهلك — حلقةٌ مضمونة.
    """
    bus = InMemoryEventBus()
    await bus.publish(
        EventEnvelope(
            event_id="dead-1",
            event_name="a",
            topic=Topic.DEAD_LETTER.value,
            payload={},
            occurred_at=datetime.now(UTC),
        )
    )

    await consumers.drain_all(bus)
    assert bus.pending(Topic.DEAD_LETTER) == 1


async def test_the_drain_summary_counts_every_outcome() -> None:
    async def subscriber(_: EventEnvelope) -> None:
        return None

    consumers.subscribe(Topic.PRODUCT_EVENTS, subscriber)
    bus = InMemoryEventBus()
    for index in range(2):
        await bus.publish(
            build_envelope(topic=Topic.PRODUCT_EVENTS, event_name=f"e{index}", payload={})
        )

    assert (await consumers.drain_all(bus))["handled"] == 2


def test_subscribing_twice_is_visible_in_the_registry() -> None:
    async def subscriber(_: EventEnvelope) -> None:
        return None

    consumers.subscribe(Topic.PRODUCT_EVENTS, subscriber)
    assert subscriber in consumers.subscribers_for(Topic.PRODUCT_EVENTS)


# ── الحلقة الخلفية ──────────────────────────────────────────────────────────────


async def test_the_relay_reports_nothing_when_the_driver_is_not_in_memory(monkeypatch) -> None:
    """مع Kafka لا يوجد ما يُسحَب محلياً — الملخّص الفارغ صادق."""
    from app.services.messaging import relay

    class RemotePublisher(EventPublisher):
        async def publish(self, envelope: EventEnvelope) -> None:
            return None

    monkeypatch.setattr(
        "app.services.messaging.runtime._build_publisher", lambda: RemotePublisher()
    )
    reset_event_publisher()

    assert await relay.run_relay_once() == {}


async def test_the_relay_handle_starts_and_stops_cleanly() -> None:
    from app.services.messaging.relay import RelayHandle

    handle = RelayHandle()
    await handle.start()
    assert handle.running is True
    await handle.stop()
    assert handle.running is False


async def test_stopping_a_relay_that_never_started_is_safe() -> None:
    from app.services.messaging.relay import RelayHandle

    await RelayHandle().stop()


async def test_registering_subscribers_is_idempotent() -> None:
    from app.services.messaging.notifications import handle_product_event, register_subscribers

    register_subscribers()
    register_subscribers()
    registered = consumers.subscribers_for(Topic.PRODUCT_EVENTS)
    assert registered.count(handle_product_event) == 1


async def test_the_relay_drains_the_in_memory_bus() -> None:
    """دورةٌ واحدة تسحب ما نُشِر فعلاً — لا حلقةٌ تدور على الفراغ."""
    from app.services.messaging import relay

    seen: list[str] = []

    async def subscriber(envelope: EventEnvelope) -> None:
        seen.append(envelope.event_name)

    consumers.subscribe(Topic.PRODUCT_EVENTS, subscriber)
    await publish_event(
        build_envelope(topic=Topic.PRODUCT_EVENTS, event_name="chat_turn_started", payload={})
    )

    assert (await relay.run_relay_once())["handled"] == 1
    assert seen == ["chat_turn_started"]


async def test_the_relay_loop_survives_a_failing_cycle(monkeypatch, caplog) -> None:
    """
    حلقةٌ خلفية تسقط بصمت تعني نظاماً يبدو حيّاً بلا استهلاك — وهو ما يمنعه §0.
    """
    import asyncio

    from app.services.messaging import relay

    calls = {"count": 0}
    stop = asyncio.Event()

    async def exploding_cycle() -> dict[str, int]:
        calls["count"] += 1
        stop.set()
        raise RuntimeError("cycle broke")

    monkeypatch.setattr(relay, "run_relay_once", exploding_cycle)
    monkeypatch.setattr(relay, "RELAY_INTERVAL_SECONDS", 0.01)

    with caplog.at_level("WARNING"):
        await asyncio.wait_for(relay.relay_loop(stop), timeout=2.0)

    assert calls["count"] >= 1
    assert "messaging_relay_cycle_failed" in caplog.text


async def test_a_retrying_event_is_labelled_as_such() -> None:
    """كل مصير يُسمّى: نتيجةٌ بلا تسمية لا تُقاس، ومقياسٌ ناقص يخفي عطباً."""

    async def subscriber(_: EventEnvelope) -> None:
        raise TimeoutError("transient")

    consumers.subscribe(Topic.PRODUCT_EVENTS, subscriber)
    bus = InMemoryEventBus()
    await bus.publish(build_envelope(topic=Topic.PRODUCT_EVENTS, event_name="a", payload={}))

    assert (await consumers.drain_all(bus))["retry"] == 1


def test_a_reachable_broker_selects_the_kafka_driver(monkeypatch) -> None:
    """
    الاختيار يجب أن يكون قابلاً للإثبات: «سيعمل مع Kafka» ادّعاءٌ حتى يُختبَر الفرع.
    """
    from app.core import config
    from app.services.messaging.kafka_publisher import KafkaEventPublisher

    settings = config.get_settings()
    monkeypatch.setattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "broker:9092", raising=False)

    assert isinstance(get_event_publisher(), KafkaEventPublisher)


async def test_a_dead_lettered_event_is_labelled_dead_letter() -> None:
    """المصير الرابع مُسمّى أيضاً — عدّادٌ بلا فئة «ميتة» يُخفي أخطر الحالات."""
    from shared.messaging import MessagingError

    async def subscriber(_: EventEnvelope) -> None:
        raise MessagingError("unreadable")

    consumers.subscribe(Topic.PRODUCT_EVENTS, subscriber)
    bus = InMemoryEventBus()
    await bus.publish(build_envelope(topic=Topic.PRODUCT_EVENTS, event_name="a", payload={}))

    assert (await consumers.drain_all(bus))["dead_letter"] == 1


async def test_a_productive_relay_cycle_is_logged(monkeypatch, caplog) -> None:
    """
    الدورة المنتجة تُسجَّل والصامتة لا: سجلٌّ يمتلئ بـ«لا شيء» يُخفي «شيئاً».
    """
    import asyncio

    from app.services.messaging import relay

    stop = asyncio.Event()
    cycles = {"count": 0}

    async def one_productive_cycle() -> dict[str, int]:
        cycles["count"] += 1
        stop.set()
        return {"handled": 1, "duplicate": 0, "dead_letter": 0, "retry": 0}

    monkeypatch.setattr(relay, "run_relay_once", one_productive_cycle)
    monkeypatch.setattr(relay, "RELAY_INTERVAL_SECONDS", 0.01)

    with caplog.at_level("INFO"):
        await asyncio.wait_for(relay.relay_loop(stop), timeout=2.0)

    assert cycles["count"] == 1
    assert "messaging_relay_cycle" in caplog.text


async def test_an_idle_relay_cycle_logs_nothing(monkeypatch, caplog) -> None:
    """دورةٌ بلا عمل تمرّ صامتة — وإلّا امتلأ السجلّ بضجيجٍ يُخفي الحوادث."""
    import asyncio

    from app.services.messaging import relay

    stop = asyncio.Event()

    async def idle_cycle() -> dict[str, int]:
        stop.set()
        return {"handled": 0, "duplicate": 0, "dead_letter": 0, "retry": 0}

    monkeypatch.setattr(relay, "run_relay_once", idle_cycle)
    monkeypatch.setattr(relay, "RELAY_INTERVAL_SECONDS", 0.01)

    with caplog.at_level("INFO"):
        await asyncio.wait_for(relay.relay_loop(stop), timeout=2.0)

    assert "messaging_relay_cycle summary" not in caplog.text

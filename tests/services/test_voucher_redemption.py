"""اختبارات استبدال القسائم وحقوق الوصول — D-198.

العقد المركزي: **استبدالٌ واحد لكلّ قسيمة، مهما تزامنت الطلبات**، و**إعادة الإرسال لا
تمنح شهرين**. الحَكَم قيدٌ في قاعدة البيانات لا فحصٌ في التطبيق — «افحص ثمّ اكتب» نافذةُ
سباق يعبرها طلبان متزامنان.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.services.billing import VoucherRedemptionError, VoucherService
from app.services.billing.vouchers import hash_code
from shared.voucher import generate_voucher_code, normalize_code


async def _make_user(db_session, email: str) -> int:
    result = await db_session.execute(
        text(
            "INSERT INTO users (external_id, full_name, email, password_hash, "
            "is_admin, is_active, status) VALUES (:e, :n, :e, 'x', 0, 1, 'active')"
        ),
        {"e": email, "n": email.split("@", maxsplit=1)[0]},
    )
    await db_session.commit()
    return int(result.lastrowid)


def _run(event_loop, coro):
    return event_loop.run_until_complete(coro)


# ── الإصدار ────────────────────────────────────────────────────────────────────


def test_the_plaintext_code_is_never_stored(event_loop, db_session) -> None:
    """
    الرمز سندٌ لحامله: تسريب نسخةٍ من قاعدة البيانات برموزٍ صريحة = اشتراكات مجانية.
    """

    async def scenario() -> None:
        service = VoucherService(db_session)
        code = await service.issue()

        stored = await db_session.scalar(text("SELECT code_hash FROM vouchers LIMIT 1"))
        assert stored == hash_code(normalize_code(code))
        assert normalize_code(code) not in stored

    _run(event_loop, scenario())


def test_issue_rejects_a_non_positive_duration(event_loop, db_session) -> None:
    async def scenario() -> None:
        with pytest.raises(VoucherRedemptionError, match="duration_days"):
            await VoucherService(db_session).issue(duration_days=0)

    _run(event_loop, scenario())


# ── الاستبدال ──────────────────────────────────────────────────────────────────


def test_redeeming_grants_an_entitlement(event_loop, db_session) -> None:
    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "redeemer@example.com")
        code = await service.issue(plan="standard", duration_days=30)

        before = await service.entitlement_status(user_id)
        assert before.active is False

        outcome = await service.redeem(user_id=user_id, raw_code=code)
        assert outcome.plan == "standard"
        assert outcome.already_redeemed_by_you is False

        after = await service.entitlement_status(user_id)
        assert after.active is True
        assert after.plan == "standard"
        assert after.expires_at is not None

    _run(event_loop, scenario())


def test_resending_the_same_request_does_not_grant_two_months(event_loop, db_session) -> None:
    """
    الـidempotency الحقيقي: شبكةٌ متقطّعة أو ضغطُ زرٍّ مزدوج لا يمنح شهرين، ولا يُرجِع
    خطأً مربكاً لمن استبدل بنجاح.
    """

    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "double-click@example.com")
        code = await service.issue(duration_days=30)

        first = await service.redeem(user_id=user_id, raw_code=code)
        second = await service.redeem(user_id=user_id, raw_code=code)

        assert second.already_redeemed_by_you is True
        assert second.expires_at == first.expires_at

        count = await db_session.scalar(text("SELECT COUNT(*) FROM entitlements"))
        assert count == 1

    _run(event_loop, scenario())


def test_another_user_cannot_reuse_a_redeemed_voucher(event_loop, db_session) -> None:
    async def scenario() -> None:
        service = VoucherService(db_session)
        owner = await _make_user(db_session, "voucher-owner@example.com")
        intruder = await _make_user(db_session, "voucher-intruder@example.com")
        code = await service.issue()

        await service.redeem(user_id=owner, raw_code=code)
        with pytest.raises(VoucherRedemptionError, match="already been redeemed"):
            await service.redeem(user_id=intruder, raw_code=code)

        assert (await service.entitlement_status(intruder)).active is False

    _run(event_loop, scenario())


def test_the_unique_constraint_is_the_real_guard(event_loop, db_session) -> None:
    """
    برهانٌ بنيوي: القيد الفريد يرفض استبدالاً ثانياً حتى لو تجاوز الكودُ الفحصَ.

    نُدرِج الصفّ مباشرةً كما يفعل طلبٌ متزامن فاز بالسباق — القاعدة ترفض الثاني.
    """

    async def scenario() -> None:
        from sqlalchemy.exc import IntegrityError

        service = VoucherService(db_session)
        user_a = await _make_user(db_session, "race-a@example.com")
        user_b = await _make_user(db_session, "race-b@example.com")
        code = await service.issue()
        voucher_id = await db_session.scalar(text("SELECT id FROM vouchers LIMIT 1"))

        await db_session.execute(
            text(
                "INSERT INTO voucher_redemptions (voucher_id, user_id, redeemed_at)"
                " VALUES (:v, :u, :t)"
            ),
            {"v": voucher_id, "u": user_a, "t": datetime.now(UTC)},
        )
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO voucher_redemptions (voucher_id, user_id, redeemed_at)"
                    " VALUES (:v, :u, :t)"
                ),
                {"v": voucher_id, "u": user_b, "t": datetime.now(UTC)},
            )
        await db_session.rollback()
        assert code

    _run(event_loop, scenario())


def test_a_second_voucher_extends_rather_than_replaces(event_loop, db_session) -> None:
    """التمديد يبدأ من نهاية الحقّ الحيّ — لا يُهدَر ما دفعه المستخدم."""

    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "extender@example.com")

        first = await service.redeem(
            user_id=user_id, raw_code=await service.issue(duration_days=30)
        )
        second = await service.redeem(
            user_id=user_id, raw_code=await service.issue(duration_days=30)
        )

        assert second.expires_at > first.expires_at
        delta = second.expires_at - first.expires_at
        assert timedelta(days=29) < delta < timedelta(days=31)

    _run(event_loop, scenario())


@pytest.mark.parametrize(
    ("code", "message"),
    [("CFRG-XXXX", "malformed"), ("not a code at all", "malformed")],
)
def test_a_malformed_code_is_refused_before_any_query(
    event_loop, db_session, code: str, message: str
) -> None:
    async def scenario() -> None:
        user_id = await _make_user(db_session, f"malformed-{abs(hash(code))}@example.com")
        with pytest.raises(VoucherRedemptionError, match=message):
            await VoucherService(db_session).redeem(user_id=user_id, raw_code=code)

    _run(event_loop, scenario())


def test_an_unknown_but_well_formed_code_is_refused(event_loop, db_session) -> None:
    async def scenario() -> None:
        user_id = await _make_user(db_session, "unknown-voucher@example.com")
        with pytest.raises(VoucherRedemptionError, match="unknown voucher"):
            await VoucherService(db_session).redeem(
                user_id=user_id, raw_code=generate_voucher_code()
            )

    _run(event_loop, scenario())


def test_a_voided_voucher_is_refused(event_loop, db_session) -> None:
    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "voided@example.com")
        code = await service.issue()
        await db_session.execute(text("UPDATE vouchers SET status = 'void'"))
        await db_session.commit()

        with pytest.raises(VoucherRedemptionError, match="voided"):
            await service.redeem(user_id=user_id, raw_code=code)

    _run(event_loop, scenario())


def test_an_expired_voucher_is_refused(event_loop, db_session) -> None:
    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "expired-voucher@example.com")
        code = await service.issue()
        await db_session.execute(
            text("UPDATE vouchers SET expires_at = :t"),
            {"t": datetime.now(UTC) - timedelta(days=1)},
        )
        await db_session.commit()

        with pytest.raises(VoucherRedemptionError, match="expired"):
            await service.redeem(user_id=user_id, raw_code=code)

    _run(event_loop, scenario())


def test_an_expired_entitlement_is_not_active(event_loop, db_session) -> None:
    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "lapsed@example.com")
        await db_session.execute(
            text(
                "INSERT INTO entitlements (user_id, plan, source, granted_at, expires_at)"
                " VALUES (:u, 'standard', 'voucher', :g, :e)"
            ),
            {
                "u": user_id,
                "g": datetime.now(UTC) - timedelta(days=60),
                "e": datetime.now(UTC) - timedelta(days=1),
            },
        )
        await db_session.commit()

        assert (await service.entitlement_status(user_id)).active is False

    _run(event_loop, scenario())


def test_the_furthest_live_entitlement_wins(event_loop, db_session) -> None:
    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "multi-entitlement@example.com")
        far = datetime.now(UTC) + timedelta(days=90)
        for expires in (datetime.now(UTC) + timedelta(days=5), far):
            await db_session.execute(
                text(
                    "INSERT INTO entitlements (user_id, plan, source, granted_at, expires_at)"
                    " VALUES (:u, 'standard', 'voucher', :g, :e)"
                ),
                {"u": user_id, "g": datetime.now(UTC), "e": expires},
            )
        await db_session.commit()

        found = await service.entitlement_status(user_id)
        assert found.active is True
        assert abs((found.expires_at - far).total_seconds()) < 2

    _run(event_loop, scenario())


def test_losing_the_race_is_translated_into_the_right_refusal(
    event_loop, db_session, monkeypatch
) -> None:
    """
    حين يفوز طلبٌ متزامن، تُرجِع القاعدة `IntegrityError` — ويجب أن تصل المستخدم
    رسالةً مفهومة («استُبدلت») لا خطأَ خادمٍ خام.
    """
    from sqlalchemy.exc import IntegrityError

    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "race-loser@example.com")
        code = await service.issue()

        async def losing_commit() -> None:
            raise IntegrityError("INSERT", {}, Exception("unique violation"))

        monkeypatch.setattr(service.db, "commit", losing_commit)
        with pytest.raises(VoucherRedemptionError, match="already been redeemed"):
            await service.redeem(user_id=user_id, raw_code=code)

    _run(event_loop, scenario())


def test_expired_rows_are_skipped_while_scanning_live_ones(event_loop, db_session) -> None:
    """مزيجٌ من المنتهي والحيّ — الماسح يتخطّى المنتهي ويختار الأبعد بين الأحياء."""

    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "mixed-entitlements@example.com")
        now = datetime.now(UTC)
        for expires in (
            now - timedelta(days=1),
            now + timedelta(days=5),
            now + timedelta(days=120),
            now + timedelta(days=30),
        ):
            await db_session.execute(
                text(
                    "INSERT INTO entitlements (user_id, plan, source, granted_at, expires_at)"
                    " VALUES (:u, 'standard', 'voucher', :g, :e)"
                ),
                {"u": user_id, "g": now, "e": expires},
            )
        await db_session.commit()

        found = await service.entitlement_status(user_id)
        assert found.active is True
        assert (found.expires_at - now).days >= 119

    _run(event_loop, scenario())


# ── نقاط النهاية ───────────────────────────────────────────────────────────────


def test_redeem_requires_authentication(client) -> None:
    assert client.post(
        "/api/v1/vouchers/redeem", json={"code": "CFRG-AAAA-AAAA-AAAA"}
    ).status_code in (
        401,
        403,
    )


def test_issue_requires_admin(event_loop, client, db_session, register_and_login_test_user) -> None:
    """إصدار القسائم يخلق قيمةً — ليس لكلّ مستخدم."""
    token = _run(event_loop, register_and_login_test_user(db_session, "not-issuer@example.com"))
    response = client.post(
        "/api/v1/vouchers/issue",
        json={"plan": "standard", "duration_days": 30, "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_the_redeem_flow_over_http(
    event_loop, client, db_session, register_and_login_test_user
) -> None:
    async def seed() -> tuple[str, str]:
        token = await register_and_login_test_user(db_session, "http-redeem@example.com")
        code = await VoucherService(db_session).issue(duration_days=30)
        return token, code

    token, code = _run(event_loop, seed())
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/vouchers/entitlement", headers=headers).json()["active"] is False

    redeemed = client.post("/api/v1/vouchers/redeem", json={"code": code}, headers=headers)
    assert redeemed.status_code == 200, redeemed.text
    assert redeemed.json()["plan"] == "standard"
    assert redeemed.json()["already_redeemed_by_you"] is False

    again = client.post("/api/v1/vouchers/redeem", json={"code": code}, headers=headers)
    assert again.status_code == 200
    assert again.json()["already_redeemed_by_you"] is True

    status_now = client.get("/api/v1/vouchers/entitlement", headers=headers).json()
    assert status_now["active"] is True
    assert status_now["plan"] == "standard"


def test_a_bad_code_over_http_is_a_400(
    event_loop, client, db_session, register_and_login_test_user
) -> None:
    token = _run(event_loop, register_and_login_test_user(db_session, "bad-voucher@example.com"))
    response = client.post(
        "/api/v1/vouchers/redeem",
        json={"code": "CFRG-ZZZZ-ZZZZ-ZZZZ"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_handlers_shape_their_responses_directly(event_loop, db_session) -> None:
    """
    نداءٌ مباشر للمعالِجات — معالِجات ASGI تحت `TestClient` تعمل في خيطٍ عامل لا
    يتتبّعه `coverage`، فيُثبَّت تحويل العقد هنا في الخيط الرئيسي.
    """
    from fastapi import HTTPException

    from app.api.routers.vouchers import (
        IssueRequest,
        RedeemRequest,
        entitlement,
        issue_vouchers,
        redeem_voucher,
    )

    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "handler-direct@example.com")
        stub = type("U", (), {"user": type("I", (), {"id": user_id})()})()

        issued = await issue_vouchers(
            payload=IssueRequest(plan="standard", duration_days=30, quantity=2),
            _=stub,
            service=service,
        )
        assert len(issued.codes) == 2

        before = await entitlement(current=stub, service=service)
        assert before.active is False

        redeemed = await redeem_voucher(
            payload=RedeemRequest(code=issued.codes[0]), current=stub, service=service
        )
        assert redeemed.plan == "standard"

        after = await entitlement(current=stub, service=service)
        assert after.active is True

        with pytest.raises(HTTPException) as excinfo:
            await redeem_voucher(
                payload=RedeemRequest(code="CFRG-ZZZZ-ZZZZ-ZZZZ"),
                current=stub,
                service=service,
            )
        assert excinfo.value.status_code == 400

    _run(event_loop, scenario())


# ── بوّابة الاشتراك ─────────────────────────────────────────────────────────────


def test_the_entitlement_gate_is_a_single_dependency(event_loop, db_session) -> None:
    """
    فحصُ الاشتراك المنسوخ في كلّ معالِج ينسى موضعاً حتماً — والموضع المنسيّ ميزةٌ
    مجانية لا يعرف بها أحد. تعريفٌ واحد يُطبَّق بالتصريح.
    """
    from fastapi import HTTPException

    from app.deps.billing import require_active_entitlement

    async def scenario() -> None:
        service = VoucherService(db_session)
        user_id = await _make_user(db_session, "gated@example.com")
        stub = type("U", (), {"user": type("I", (), {"id": user_id})()})()

        with pytest.raises(HTTPException) as excinfo:
            await require_active_entitlement(current=stub, service=service)
        assert excinfo.value.status_code == 402

        await service.redeem(user_id=user_id, raw_code=await service.issue())
        assert await require_active_entitlement(current=stub, service=service) is stub

    _run(event_loop, scenario())

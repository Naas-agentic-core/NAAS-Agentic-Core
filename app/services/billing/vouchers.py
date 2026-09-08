"""
إصدار القسائم واستبدالها ومنح حقوق الوصول (D-198).

**الاستبدال idempotent للفاعل نفسه، ومرفوض لغيره.** إعادة إرسال الطلب (شبكةٌ متقطّعة،
ضغطُ زرٍّ مزدوج) لا تمنح شهرين ولا تُرجِع خطأً مربكاً؛ تُرجِع نفس الحقّ. أمّا مستخدمٌ
آخر يجرّب رمزاً مُستهلَكاً فيُرفَض.

**الحَكَم قيدٌ في قاعدة البيانات لا فحصٌ في التطبيق.** «افحص هل استُبدلت ثمّ اكتب» نافذةُ
سباق: طلبان متزامنان يقرآن «لا» فيكتبان معاً فيُمنَح شهران بقسيمةٍ واحدة. القيد الفريد
على `voucher_redemptions.voucher_id` هو ما يمنع ذلك فعلاً، والكود يلتقط `IntegrityError`
ويترجمها إلى النتيجة الصحيحة.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.voucher import Entitlement, Voucher, VoucherRedemption
from shared.voucher import VoucherError, generate_voucher_code, validate_code

logger = logging.getLogger("cogniforge.billing.vouchers")


class VoucherRedemptionError(ValueError):
    """سببٌ صريح لفشل الاستبدال — يُترجَم إلى رسالة للمستخدم."""


@dataclass(frozen=True)
class RedemptionOutcome:
    """نتيجة الاستبدال. `already_redeemed_by_you` تعني إعادة إرسالٍ لا خطأً."""

    plan: str
    expires_at: datetime
    already_redeemed_by_you: bool = False


@dataclass(frozen=True)
class EntitlementStatus:
    """حالة اشتراك مستخدمٍ الآن."""

    active: bool
    plan: str | None
    expires_at: datetime | None


def hash_code(payload: str) -> str:
    """SHA-256 للرمز المُطبَّع — ما يُخزَّن ويُطابَق."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


class VoucherService:
    """يُصدِر القسائم ويستبدلها ويقرأ الحقوق — ضمن جلسة `AsyncSession` واحدة."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def issue(
        self, *, plan: str = "standard", duration_days: int = 30, valid_for_days: int = 365
    ) -> str:
        """يُصدِر قسيمة ويُرجِع رمزها **الصريح مرّة واحدة** — لا يُخزَّن إلّا مُجزَّأً."""
        if duration_days <= 0:
            raise VoucherRedemptionError("duration_days must be positive")
        code = generate_voucher_code()
        self.db.add(
            Voucher(
                code_hash=hash_code(validate_code(code)),
                plan=plan,
                duration_days=duration_days,
                status="issued",
                expires_at=datetime.now(UTC) + timedelta(days=valid_for_days),
            )
        )
        await self.db.commit()
        return code

    async def redeem(self, *, user_id: int, raw_code: str) -> RedemptionOutcome:
        """يستبدل قسيمة ويمنح الحقّ. idempotent للفاعل نفسه."""
        try:
            payload = validate_code(raw_code)
        except VoucherError as exc:
            # الفحص البنيوي يسبق أيّ استعلام: خطأٌ مطبعي يُردّ برسالته الصحيحة بدل
            # «قسيمة مجهولة» التي تدفع المستخدم لطلب استرداد بدل تصحيح حرف.
            raise VoucherRedemptionError(str(exc)) from exc

        voucher = await self.db.scalar(
            select(Voucher).where(Voucher.code_hash == hash_code(payload))
        )
        if voucher is None:
            raise VoucherRedemptionError("unknown voucher code")
        if voucher.status == "void":
            raise VoucherRedemptionError("this voucher has been voided")
        if voucher.expires_at is not None and _as_utc(voucher.expires_at) < datetime.now(UTC):
            raise VoucherRedemptionError("this voucher has expired")

        existing = await self.db.scalar(
            select(VoucherRedemption).where(VoucherRedemption.voucher_id == voucher.id)
        )
        if existing is not None:
            if existing.user_id != user_id:
                raise VoucherRedemptionError("this voucher has already been redeemed")
            # إعادة إرسال من صاحب الاستبدال نفسه — نُرجِع الحقّ القائم بلا تمديد.
            status = await self.entitlement_status(user_id)
            return RedemptionOutcome(
                plan=voucher.plan,
                expires_at=status.expires_at or _as_utc(existing.redeemed_at),
                already_redeemed_by_you=True,
            )

        now = datetime.now(UTC)
        # التمديد يبدأ من نهاية الحقّ القائم إن كان حيّاً — لا يُهدَر ما دفعه المستخدم.
        current = await self.entitlement_status(user_id)
        starts_from = (
            current.expires_at if current.active and current.expires_at is not None else now
        )
        expires_at = starts_from + timedelta(days=voucher.duration_days)

        # ⚠️ نلتقط المعرّف والخطّة **قبل** أيّ commit/rollback: بعد `rollback()` تصير
        # كائنات ORM مُنتهية الصلاحية، فأيّ قراءة لحقلٍ منها تُطلِق استعلام تحديثٍ كسول
        # يرفع داخل معالج الاستثناء — فيضيع سببُ الفشل الحقيقي خلف خطأٍ ثانٍ مُربك.
        voucher_id = voucher.id
        plan = voucher.plan

        self.db.add(VoucherRedemption(voucher_id=voucher_id, user_id=user_id, redeemed_at=now))
        self.db.add(
            Entitlement(
                user_id=user_id,
                plan=plan,
                source="voucher",
                granted_at=now,
                expires_at=expires_at,
            )
        )
        voucher.status = "redeemed"
        self.db.add(voucher)
        try:
            await self.db.commit()
        except IntegrityError:
            # سباقٌ خسرناه: القيد الفريد رفض الاستبدال الثاني. هذا هو الحارس الحقيقي.
            await self.db.rollback()
            logger.info("voucher_redeem_race voucher_id=%s user_id=%s", voucher_id, user_id)
            raise VoucherRedemptionError("this voucher has already been redeemed") from None

        logger.info(
            "voucher_redeemed voucher_id=%s user_id=%s plan=%s until=%s",
            voucher_id,
            user_id,
            plan,
            expires_at,
        )
        return RedemptionOutcome(plan=plan, expires_at=expires_at)

    async def entitlement_status(self, user_id: int) -> EntitlementStatus:
        """أبعد حقٍّ حيّ للمستخدم، أو `active=False`."""
        stmt = (
            select(Entitlement)
            .where(Entitlement.user_id == user_id)
            .order_by(Entitlement.expires_at.desc(), Entitlement.id.desc())
            .limit(1)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None or _as_utc(row.expires_at) <= now:
            return EntitlementStatus(active=False, plan=None, expires_at=None)
        return EntitlementStatus(active=True, plan=row.plan, expires_at=_as_utc(row.expires_at))


__all__ = [
    "EntitlementStatus",
    "RedemptionOutcome",
    "VoucherRedemptionError",
    "VoucherService",
    "hash_code",
]

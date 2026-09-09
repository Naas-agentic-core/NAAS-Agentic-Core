"""
Voucher / Entitlement Domain Models (D-198).

**الرمز يُخزَّن مُجزَّأً (hash) لا صريحاً.** رمز القسيمة **سندٌ لحامله**: من يقرأه يستطيع
استبداله. تسريبُ نسخةٍ من قاعدة البيانات مع رموزٍ صريحة يعني اشتراكاتٍ مجانية لكلّ من
اطّلع عليها. التجزئة تسمح بالبحث (نُجزّئ المُدخَل ونطابق) وتمنع القراءة العكسية.

**الاستبدال الواحد مفروضٌ بقيد فريد في قاعدة البيانات** (`voucher_redemptions.voucher_id`)
لا بفحصٍ في التطبيق: فحص «هل استُبدلت؟» ثمّ الكتابة نافذةُ سباق — طلبان متزامنان يقرآن
«لا» فيكتبان معاً. القيد الفريد هو الحَكَم الوحيد الذي لا يُخدَع.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, func
from sqlmodel import Field, SQLModel

from app.core.domain.common import utc_now


class Voucher(SQLModel, table=True):
    """قسيمة مدفوعة مسبقاً — تُصدَر مرّة وتُستبدَل مرّة."""

    __tablename__ = "vouchers"

    id: int | None = Field(default=None, primary_key=True)
    #: SHA-256 للرمز المُطبَّع. لا يُخزَّن الرمز الصريح أبداً.
    code_hash: str = Field(max_length=64, index=True)
    plan: str = Field(default="standard", max_length=32)
    duration_days: int = Field(default=30)
    status: str = Field(default="issued", max_length=16)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class VoucherRedemption(SQLModel, table=True):
    """استبدالٌ واحد. `voucher_id` فريد — القيد هو ما يمنع الاستبدال المزدوج."""

    __tablename__ = "voucher_redemptions"

    id: int | None = Field(default=None, primary_key=True)
    voucher_id: int = Field(foreign_key="vouchers.id", index=True, unique=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    redeemed_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )


class Entitlement(SQLModel, table=True):
    """حقّ وصولٍ ممنوح لمستخدم حتى `expires_at`."""

    __tablename__ = "entitlements"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    plan: str = Field(default="standard", max_length=32)
    source: str = Field(default="voucher", max_length=32)
    granted_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    expires_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )


__all__ = ["Entitlement", "Voucher", "VoucherRedemption"]

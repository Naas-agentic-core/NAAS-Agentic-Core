"""
أدوات الأمان الأساسية (Core Security Utilities).

يتضمن هذا الملف دوال للتعامل مع رموز JWT، كلمات المرور، وعمليات التشفير الأخرى.
جميع الدوال في هذا النموذج مصممة لتكون نقية (Pure) ومستقلة عن إطار العمل.

المبادئ (Principles):
- Security First: تطبيق أفضل الممارسات الأمنية (HS256, Bcrypt/Argon2).
- Framework Agnostic: يمكن استخدامه في أي جزء من التطبيق.
- CS50 2025: توثيق عربي واضح.
"""

from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from app.security.passwords import pwd_context


def generate_service_token(user_id: str) -> str:
    """
    توليد رمز JWT قصير الأجل للمصادقة مع الخدمات الداخلية.

    تقوم هذه الدالة بإنشاء رمز مميز بوقت انتهاء صلاحية قصير جداً (5 دقائق)
    مخصص للاتصال بين الخدمات حيث تكون الأولوية لزمن الاستجابة المنخفض والأمان العالي.

    Args:
        user_id (str): المعرف الفريد للمستخدم أو الخدمة التي تطلب الرمز.

    Returns:
        str: رمز JWT موقع ومشفر باستخدام خوارزمية HS256.
    """
    payload = {
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "iat": datetime.now(UTC),
        "sub": user_id,
    }
    current_settings = get_settings()
    return jwt.encode(payload, current_settings.SECRET_KEY, algorithm="HS256")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    التحقق من كلمة المرور مقابل التجزئة (Hash) باستخدام سياق كلمة المرور المكون عالمياً.

    يضمن هذا التجريد منطق تحقق متسق لكلمات المرور عبر التطبيق،
    مع الاستفادة من أفضل الممارسات لمنع هجمات التوقيت (Timing Attacks).

    Args:
        plain_password (str): كلمة المرور النصية التي قدمها المستخدم.
        hashed_password (str): تجزئة bcrypt/argon2 المخزنة في قاعدة البيانات.

    Returns:
        bool: True إذا كانت كلمة المرور تطابق التجزئة، وإلا False.
    """
    return pwd_context.verify(plain_password, hashed_password)

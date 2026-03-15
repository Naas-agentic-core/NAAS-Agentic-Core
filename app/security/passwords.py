"""
سياق كلمات المرور الموحّد (Unified Password Context).

يوفر هذا الملف سياق التشفير المركزي لكلمات المرور بحيث يتم استخدامه
عبر جميع طبقات التطبيق دون تسريب المنطق الأمني إلى النماذج.
"""

import os

from passlib.context import CryptContext

os.environ.setdefault("PASSLIB_BUILTIN_BCRYPT", "enabled")

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt", "pbkdf2_sha256", "sha256_crypt"],
    deprecated="auto",
)

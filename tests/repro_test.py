from passlib.context import CryptContext


def test_bcrypt_backend_available():
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = ctx.hash("probe")
    assert ctx.verify("probe", hashed)

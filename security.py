from __future__ import annotations
import base64, hashlib, hmac, os, secrets, struct, time
from urllib.parse import quote

PBKDF2_ROUNDS = 310_000

def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("password too short")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_b64, digest_b64 = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def constant_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))

def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

def _b32decode(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    s += "=" * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s, casefold=True)

def totp_code(secret: str, at_time: int | None = None, step: int = 30, digits: int = 6) -> str:
    at_time = int(time.time() if at_time is None else at_time)
    counter = at_time // step
    msg = struct.pack(">Q", counter)
    digest = hmac.new(_b32decode(secret), msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset+4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return f"{value:0{digits}d}"

def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    now = int(time.time())
    return any(hmac.compare_digest(totp_code(secret, now + delta * 30), code) for delta in range(-window, window + 1))

def otpauth_uri(secret: str, account: str, issuer: str = "Immobilienservice Steinbach") -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"

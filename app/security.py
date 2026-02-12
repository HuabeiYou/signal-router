import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import URLSafeSerializer, URLSafeTimedSerializer

from app.config import settings


def _derive_fernet_key(raw: str) -> bytes:
    if raw:
        try:
            Fernet(raw.encode("utf-8"))
            return raw.encode("utf-8")
        except Exception:
            pass
    digest = hashlib.sha256((raw or "dev-fernet-key").encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


fernet = Fernet(_derive_fernet_key(settings.fernet_key))
session_serializer = URLSafeTimedSerializer(settings.session_secret, salt="admin-session")
csrf_serializer = URLSafeSerializer(settings.session_secret, salt="admin-csrf")


def encrypt_text(value: str) -> str:
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str) -> Optional[str]:
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def mask_webhook(url: str) -> str:
    if "key=" not in url:
        if len(url) <= 12:
            return "***"
        return f"{url[:6]}***{url[-4:]}"
    prefix, key = url.rsplit("key=", 1)
    if len(key) <= 8:
        return f"{prefix}key=***"
    return f"{prefix}key={key[:4]}***{key[-4:]}"


def build_session_token(username: str) -> str:
    return session_serializer.dumps({"username": username})


def parse_session_token(token: str) -> Optional[str]:
    try:
        data = session_serializer.loads(token, max_age=settings.admin_session_ttl_seconds)
        return data.get("username")
    except Exception:
        return None


def build_csrf_token(username: str) -> str:
    return csrf_serializer.dumps({"username": username})


def verify_csrf_token(token: str, username: str) -> bool:
    try:
        data = csrf_serializer.loads(token)
    except Exception:
        return False
    return data.get("username") == username

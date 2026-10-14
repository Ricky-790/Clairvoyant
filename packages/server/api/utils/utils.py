import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from fastapi.exceptions import HTTPException

load_dotenv()

_FERNET_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
if not _FERNET_KEY:
    raise RuntimeError(
        "TOKEN_ENCRYPTION_KEY is not set. Generate one with: "
        'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
    )
try:
    _fernet = Fernet(_FERNET_KEY)
except (TypeError, ValueError) as exc:
    # Fernet keys are 32 url-safe base64-encoded bytes (44 chars).
    raise RuntimeError(
        f"TOKEN_ENCRYPTION_KEY is not a valid Fernet key: {exc}"
    ) from exc


def encrypt_token(value: str | bytes) -> bytes:
    """Encrypt a GitHub token for storage. Accepts str or bytes, returns bytes."""
    if isinstance(value, str):
        value = value.encode("utf-8")
    return _fernet.encrypt(value)


def decrypt_token(value: bytes) -> str:
    """Decrypt a stored token back to its original string.

    Raises:
        cryptography.fernet.InvalidToken: if the value is corrupted, or was
            encrypted with a different key (e.g. TOKEN_ENCRYPTION_KEY rotated).
    """
    return _fernet.decrypt(bytes(value)).decode("utf-8")


WEBHOOK_SECRET = os.getenv("GH_WEBHOOK_SECRET", "")


def verify_signature(payload_body: bytes, signature_header: str | None):
    if not signature_header:
        raise HTTPException(401, "Missing signature")
    if WEBHOOK_SECRET == "":
        raise RuntimeError(
            "GH_WEBHOOK_SECRET is not set. Set it to the webhook secret configured in GitHub."
        )
    secret = WEBHOOK_SECRET.encode()
    expected = "sha256=" + hmac.new(secret, payload_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(401, "Invalid signature")


BUCKET_URI = os.getenv("BUCKET_URI", "")


def dump_to_bucket(file):
    pass

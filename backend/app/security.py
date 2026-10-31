import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from app.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


ADMIN_HASH = hash_password(settings.ADMIN_PASSWORD)


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {"sub": subject, "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username != settings.ADMIN_USERNAME:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )


def mask_pan(pan: str) -> str:
    """Mask PAN leaving first 6 and last 4 digits visible."""
    clean = re.sub(r"\D", "", str(pan or ""))
    if len(clean) < 10:
        return "****"
    return f"{clean[:6]}{'*' * (len(clean) - 10)}{clean[-4:]}"


def tokenize_pan(pan: str) -> str:
    """Create deterministic non-reversible token for test card lookup."""
    clean = re.sub(r"\D", "", str(pan or ""))
    digest = hashlib.sha256((clean + settings.SECRET_KEY).encode("utf-8")).hexdigest()[:24].upper()
    return f"TKN_{digest}"


SENSITIVE_KEYS = {
    "pin", "clear_pin", "pin_block", "de52", "f52", "f63",
    "cvv", "cvv2", "icvv", "pvv", "clear_key", "key_material",
    "track2", "de35", "f35", "track1", "de45", "f45", "pan", "de2", "f2"
}


def sanitize_dict(data: Any) -> Any:
    """Recursively mask sensitive fields in dictionaries before logging or saving."""
    if isinstance(data, dict):
        sanitized: Dict[str, Any] = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if k_lower in {"pan", "de2", "f2", "card_number"} and isinstance(v, str):
                sanitized[k] = mask_pan(v)
            elif any(s in k_lower for s in ("pin", "cvv", "pvv", "clear_key", "track")):
                sanitized[k] = "***MASKED***"
            else:
                sanitized[k] = sanitize_dict(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_dict(item) for item in data]
    return data


def mask_raw_tic_message(raw_msg: str) -> str:
    """Mask PAN and PIN block sequences inside raw or compact TIC strings."""
    if not raw_msg:
        return ""
    masked = re.sub(
        r"(F2\))(\d{6})(\d+)(\d{4})",
        lambda m: f"{m.group(1)}{m.group(2)}{'*' * len(m.group(3))}{m.group(4)}",
        raw_msg,
    )
    masked = re.sub(r"(F52\))([0-9A-Fa-f]{16})", r"\1****************", masked)
    masked = re.sub(r"(F35\))([^\xdd]+)", r"\1***TRACK2_MASKED***", masked)
    return masked

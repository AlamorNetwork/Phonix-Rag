import logging
import re
import sys

# Narrow patterns for known credential *shapes* (API key prefixes, bearer tokens). Deliberately
# does not blanket-mask any long alphanumeric run — that would also hide legitimate audit data
# like git commit SHAs and request IDs, which is exactly what the audit trail needs to keep.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{10,}", re.IGNORECASE),
]

_known_secrets: list[str] = []


def register_secret(value: str) -> None:
    """Register a known secret value (e.g. an API key loaded from env) so it is masked
    literally wherever it appears, in addition to the shape-based patterns above."""
    if value and value not in _known_secrets:
        _known_secrets.append(value)


def mask_secrets(text: str) -> str:
    if not text:
        return text
    masked = text
    for secret in _known_secrets:
        masked = masked.replace(secret, _mask_value(secret))
    for pattern in _SECRET_PATTERNS:
        masked = pattern.sub(lambda m: _mask_value(m.group(0)), masked)
    return masked


def _mask_value(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}{'*' * (len(value) - 6)}{value[-3:]}"


class SecretMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_secrets(record.msg)
        return True


def configure_logging() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    register_secret(settings.liara_api_key)
    register_secret(settings.jwt_secret)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(SecretMaskingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [handler]

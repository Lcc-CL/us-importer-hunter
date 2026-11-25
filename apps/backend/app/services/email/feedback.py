"""Authentication for provider events normalized by a trusted adapter."""

import re
from datetime import datetime
from hmac import compare_digest, digest

MAIL_FEEDBACK_MAX_BYTES = 8192
MAIL_FEEDBACK_CLOCK_SKEW_SECONDS = 300

_TIMESTAMP = re.compile(r"[0-9]{1,12}")
_SIGNATURE = re.compile(r"v1=[0-9a-f]{64}")
_CONTEXT = b"hunter-mail-feedback-v1."


def valid_feedback_signature(
    secret: str,
    timestamp: str,
    signature: str,
    body: bytes,
    *,
    now: datetime,
) -> bool:
    if not secret or not _TIMESTAMP.fullmatch(timestamp) or not _SIGNATURE.fullmatch(signature):
        return False
    if abs(int(timestamp) - now.timestamp()) > MAIL_FEEDBACK_CLOCK_SKEW_SECONDS:
        return False
    data = _CONTEXT + timestamp.encode("ascii") + b"." + body
    expected = f"v1={digest(secret.encode(), data, 'sha256').hex()}"
    return compare_digest(expected, signature)

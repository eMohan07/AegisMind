from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_REDACTION = "[REDACTED]"

# (label, compiled pattern)
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private_key_header",
        re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
    ),
    (
        "api_key_assignment",
        re.compile(
            r'(?:api[_\-]?key|apikey|api[_\-]?secret|access[_\-]?key)'
            r'\s*[=:]\s*["\']?([A-Za-z0-9_\-\.]{16,})["\']?',
            re.IGNORECASE,
        ),
    ),
    (
        "password_assignment",
        re.compile(
            r'(?:password|passwd|pwd|db[_\-]?pass|secret)\s*[=:]\s*["\']?([^\s"\'\n]{6,})["\']?',
            re.IGNORECASE,
        ),
    ),
    (
        "bearer_token",
        re.compile(r"Bearer\s+([A-Za-z0-9\-_\.]{20,})", re.IGNORECASE),
    ),
    (
        "aws_access_key",
        re.compile(r"\b(?:AKIA|ASIA|AROA|AIDA|ANPA|ANVA)[A-Z0-9]{16}\b"),
    ),
    (
        "github_token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    ),
    (
        "private_key_pem_body",
        re.compile(r"-----END\s+(?:RSA\s+|EC\s+|DSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
    ),
]


def scan_content(content: str) -> tuple[bool, str, str | None]:
    """Scan *content* for secret material.

    Returns:
        (is_safe, sanitised_content, detected_pattern_name | None)

    When a secret is detected the function:
    - Sets is_safe=False
    - Returns a version with the matched portion replaced by "[REDACTED]"
    - Logs a WARNING (never the actual secret value)

    The caller is responsible for deciding whether to reject the content
    entirely or store the sanitised version.
    """
    detected: str | None = None
    sanitised = content

    for label, pattern in _PATTERNS:
        if pattern.search(sanitised):
            detected = label
            sanitised = pattern.sub(_REDACTION, sanitised)
            logger.warning(
                "secret_guard: pattern '%s' matched in memory content; secret redacted",
                label,
            )

    if detected is not None:
        return False, sanitised, detected
    return True, content, None

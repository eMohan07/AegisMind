from __future__ import annotations

import logging
import re
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Known prompt injection signatures and adversarial instruction patterns
ADVERSARIAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?i)\b(ignore|disregard|forget|override)\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|commands|rules)\b",
        ),
        "[NEUTRALIZED_INJECTION_DIRECTIVE]",
    ),
    (
        re.compile(
            r"(?i)\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(in\s+)?(developer\s+mode|dan|jailbreak|unrestricted)\b",
        ),
        "[NEUTRALIZED_JAILBREAK_ROLEPLAY]",
    ),
    (
        re.compile(
            r"(?i)<\s*(system|prompt|instruction|script)\s*>|<\s*/\s*(system|prompt|instruction|script)\s*>",
        ),
        "[NEUTRALIZED_SYSTEM_TAG]",
    ),
    (
        re.compile(
            r"(?i)\b(system\s*:\s*you\s+must|assistant\s*:\s*understood|human\s*:\s*override)\b",
        ),
        "[NEUTRALIZED_ROLE_OVERRIDE]",
    ),
    (
        re.compile(
            r"(?i)\b(do\s+not\s+reveal|keep\s+this\s+secret\s+and\s+print)\s+.*?\b",
        ),
        "[NEUTRALIZED_LEAK_DIRECTIVE]",
    ),
]


class SanitizationResult(NamedTuple):
    """Result of chunk text sanitization pass."""

    cleaned_text: str
    stripped_patterns: list[str]


class IngestionSanitizer:
    """Pre-embedding sanitizer neutralizing indirect prompt injections and instructions."""

    def __init__(self, patterns: list[tuple[re.Pattern[str], str]] | None = None) -> None:
        self.patterns = patterns or ADVERSARIAL_PATTERNS

    def sanitize(self, text: str, chunk_id: str | None = None) -> SanitizationResult:
        """Scan text and neutralize instruction-like patterns before chunk storage.

        Args:
            text: Raw extracted chunk text.
            chunk_id: Optional chunk identifier for audit logging.

        Returns:
            SanitizationResult with cleaned text and list of stripped patterns.
        """
        current_text = text
        stripped: list[str] = []

        for pattern, replacement in self.patterns:
            matches = pattern.findall(current_text)
            if matches:
                for match in matches:
                    pattern_str = match if isinstance(match, str) else " ".join(match)
                    stripped.append(pattern_str.strip())
                    logger.warning(
                        "Indirect prompt injection neutralized in chunk '%s': pattern='%s'",
                        chunk_id or "unknown",
                        pattern_str.strip(),
                    )
                current_text = pattern.sub(replacement, current_text)

        return SanitizationResult(cleaned_text=current_text, stripped_patterns=stripped)

"""Privacy controls — Redaction of PII/secrets before storage."""

from __future__ import annotations

import re
from typing import Any

# Standard PII patterns for redaction
_REDACTION_RULES = [
    # US Social Security Number (strict 3-2-4 with hyphens)
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),

    # Credit Card (13-19 digits, handling spaces/hyphens)
    # Using a common heuristic for 16-digit cards
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[REDACTED_CARD]"),

    # Phone Numbers (US/International heuristic)
    (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[REDACTED_PHONE]"),

    # Email Addresses
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"), "[REDACTED_EMAIL]"),
]

class RedactionPolicy:
    """Policy for scrubbing sensitive data from payloads before storage."""

    def __init__(
        self,
        active: bool = True,
        custom_rules: list[tuple[re.Pattern[str], str]] | None = None,
    ) -> None:
        self.active = active
        self.rules = _REDACTION_RULES.copy()
        if custom_rules:
            self.rules.extend(custom_rules)

    def redact_text(self, text: str) -> str:
        """Redact PII from a string."""
        if not self.active or not text:
            return text

        redacted = text
        for pattern, replacement in self.rules:
            redacted = pattern.sub(replacement, redacted)

        return redacted

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact string values inside a dictionary."""
        if not self.active:
            return data

        redacted_data: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                redacted_data[key] = self.redact_text(value)
            elif isinstance(value, dict):
                redacted_data[key] = self.redact_dict(value)
            elif isinstance(value, list):
                redacted_data[key] = self.redact_list(value)
            else:
                redacted_data[key] = value

        return redacted_data

    def redact_list(self, data: list[Any]) -> list[Any]:
        """Recursively redact string values inside a list."""
        if not self.active:
            return data

        redacted_list: list[Any] = []
        for item in data:
            if isinstance(item, str):
                redacted_list.append(self.redact_text(item))
            elif isinstance(item, dict):
                redacted_list.append(self.redact_dict(item))
            elif isinstance(item, list):
                redacted_list.append(self.redact_list(item))
            else:
                redacted_list.append(item)

        return redacted_list

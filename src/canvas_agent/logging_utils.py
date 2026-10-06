"""Logging helpers that never expose secrets."""

from __future__ import annotations

import logging
import re
from typing import Iterable


_SENSITIVE_PATTERNS = [
    re.compile(r"(Bearer\s+)(\S+)", re.IGNORECASE),
    re.compile(r"(CANVAS_TOKEN[=:\s]+)(\S+)", re.IGNORECASE),
    re.compile(r"(PARLEY_API_KEY[=:\s]+)(\S+)", re.IGNORECASE),
    re.compile(r"(ANTHROPIC_API_KEY[=:\s]+)(\S+)", re.IGNORECASE),
    re.compile(r"(OPENAI_API_KEY[=:\s]+)(\S+)", re.IGNORECASE),
    re.compile(r"(api[_-]?key[=:\s]+)(\S+)", re.IGNORECASE),
]


def redact(text: str, extra_secrets: Iterable[str] | None = None) -> str:
    redacted = text
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1***REDACTED***", redacted)
    if extra_secrets:
        for secret in extra_secrets:
            if secret:
                redacted = redacted.replace(secret, "***REDACTED***")
    return redacted


class RedactingFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str] | None = None) -> None:
        super().__init__()
        self._secrets = [s for s in (secrets or []) if s]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg, self._secrets)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact(str(v), self._secrets) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact(str(a), self._secrets) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def setup_logging(level: int = logging.INFO, secrets: Iterable[str] | None = None) -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    redactor = RedactingFilter(secrets)
    for handler in root.handlers:
        handler.addFilter(redactor)
    # Also attach to canvas_agent loggers created later
    logging.getLogger("canvas_agent").addFilter(redactor)

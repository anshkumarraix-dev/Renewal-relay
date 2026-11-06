"""Structured logging configuration with automated redaction of sensitive credentials and payment data.

Rule: Never log access tokens, client secrets, PANs (credit card numbers), or CVVs.
"""

import logging
import re
from typing import Any
from app.core.config import settings

# Regex patterns for sensitive tokens, credentials, and payment data
REDACTION_PATTERNS = [
    # Authorization header / Bearer tokens
    (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # Access token parameters / JSON fields
    (re.compile(r'("?(?:access_token|client_secret|refresh_token)"?\s*[:=]\s*"?[^"&\s]+"?)(?!\])', re.IGNORECASE), r"[REDACTED_SECRET]"),
    # Credit Card Numbers / PAN (13 to 19 digits with optional spaces or dashes)
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[REDACTED_PAN]"),
    # CVV / CVC (3 or 4 digits preceded by cvv/cvc indicators)
    (re.compile(r"(cvv|cvc|security_code)\s*[:=]\s*\d{3,4}", re.IGNORECASE), r"\1=[REDACTED_CVV]"),
]


class SensitiveDataFilter(logging.Filter):
    """Logging filter that scrubs sensitive credentials, tokens, and payment numbers."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._sanitize_value(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self._sanitize_value(v) for v in record.args)

        return True

    def _redact(self, text: str) -> str:
        for pattern, replacement in REDACTION_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _sanitize_value(self, val: Any) -> Any:
        if isinstance(val, str):
            return self._redact(val)
        return val


def setup_logging() -> None:
    """Initialize structured logging with sensitive data redaction."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
    filter_instance = SensitiveDataFilter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.addFilter(filter_instance)
        root_logger.addHandler(console_handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)
            handler.addFilter(filter_instance)

    # Apply filter to uvicorn and app loggers
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi", "sqlalchemy.engine"):
        target_logger = logging.getLogger(logger_name)
        target_logger.addFilter(filter_instance)

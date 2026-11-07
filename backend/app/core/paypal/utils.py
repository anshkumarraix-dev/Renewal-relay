"""Shared utility functions for the PayPal REST integration.

Provides:
- parse_retry_after: RFC 7231 numeric seconds and HTTP-date parsing.
- extract_debug_id: Non-fabricating PayPal-Debug-Id extractor.
- validate_api_path: Strict relative API path validator.
"""

from datetime import datetime, timezone
import email.utils
import logging
from typing import Optional
from urllib.parse import urlsplit
import httpx

logger = logging.getLogger("renewal_relay.paypal.utils")


def parse_retry_after(header_value: Optional[str]) -> Optional[float]:
    """Parse a Retry-After header into fractional seconds.

    Supports both integer seconds (RFC 7231 §7.1.3) and HTTP-date timestamps.
    Returns None if missing or malformed.
    """
    if not header_value:
        return None
    val = header_value.strip()

    # Try numeric seconds
    try:
        seconds = float(val)
        return max(0.0, seconds)
    except ValueError:
        pass

    # Try HTTP-date
    try:
        dt = email.utils.parsedate_to_datetime(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = (dt - now).total_seconds()
        return max(0.0, diff)
    except Exception:
        return None


def extract_debug_id(response: Optional[httpx.Response]) -> Optional[str]:
    """Extract optional debug_id from response header or JSON body.

    Never fabricates a synthetic debug ID.
    """
    if response is None:
        return None

    # Check case-insensitive header
    header_debug_id = response.headers.get("paypal-debug-id")
    if header_debug_id:
        return header_debug_id.strip()

    # Fallback: check JSON body attribute
    try:
        body = response.json()
        if isinstance(body, dict) and "debug_id" in body and isinstance(body["debug_id"], str):
            return body["debug_id"].strip()
    except Exception:
        pass

    return None


def validate_api_path(path: str) -> str:
    """Validate that the request path is a clean, relative PayPal API path.

    Rejects absolute URLs, scheme-relative URLs, external hostnames, embedded credentials,
    embedded query strings (must use 'params'), and URL fragments.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("PayPal API path must be a non-empty string.")

    raw = path.strip()

    # Reject scheme-relative URLs like '//example.com/path' or leading backslashes
    if raw.startswith("//") or raw.startswith("\\\\"):
        raise ValueError(f"Scheme-relative paths are strictly prohibited: '{path}'")

    # Reject absolute URLs and URL schemes like 'http://', 'https://', 'ftp://'
    if "://" in raw or raw.startswith("http:") or raw.startswith("https:"):
        raise ValueError(
            f"Absolute URLs are strictly prohibited: '{path}'. "
            "Requests are pinned to PAYPAL_BASE_URL and must specify relative paths only."
        )

    # Reject embedded query strings (caller must use dedicated 'params' argument)
    if "?" in raw:
        raise ValueError(
            f"Embedded query strings in path are prohibited: '{path}'. "
            "Pass query parameters using the 'params' dictionary argument."
        )

    # Reject URL fragments
    if "#" in raw:
        raise ValueError(f"URL fragments in path are prohibited: '{path}'.")

    try:
        parsed = urlsplit(raw)
    except Exception as exc:
        raise ValueError(f"Malformed PayPal API path: {exc}") from exc

    if parsed.scheme or parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            f"Invalid API path: '{path}'. Schemes, hostnames, credentials, queries, and fragments are prohibited."
        )

    # Normalize to start with '/'
    clean_path = raw if raw.startswith("/") else f"/{raw}"
    return clean_path

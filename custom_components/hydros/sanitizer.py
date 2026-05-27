"""Sanitize debug payloads before exposing them as HA state attributes.

The Hydros cloud / MQTT debug snapshots contain a mix of operational
data (helpful for troubleshooting) and credentials / identifiers /
tokens that should not flow into HA's recorder, exported databases,
or shared log dumps.

This module walks an arbitrary JSON-shaped payload and replaces
sensitive content with ``[REDACTED]`` placeholders, preserving the
structure so downstream debug consumers can still reason about shape.

Use :func:`sanitize_payload` for the standard sanitizer. Pass
``unsanitized=True`` to bypass redaction (gated by the
``unsanitized_debug`` options-flow toggle which defaults to ``False``).

Refs: Issue #6 (MQTT debug-sample sanitization), v0.4.0 hardening set.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

REDACTED_PLACEHOLDER = "[REDACTED]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_TOKEN = "[REDACTED_TOKEN]"
REDACTED_PRESIGNED = "[REDACTED_PRESIGNED_URL]"
REDACTED_MQTT_CREDS = "[REDACTED_MQTT_CREDS]"


# Dict keys whose VALUE should be wholesale redacted.
# Matched case-insensitively as substrings.
SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "credential",
    "token",
    "apikey",
    "api_key",
    "api-key",
    "signature",
    "serial",
    "accountid",
    "account_id",
    "userid",
    "user_id",
    "useremail",
    "user_email",
    "email",
    "cookie",
    "session",
    "x-amz-",
    "aws_access",
    "aws_secret",
    "licensekey",
    "license_key",
    "productkey",
    "product_key",
)

# Substring matches we deliberately allow through so that debug output
# remains useful. ``thingId`` / ``thingName`` are device-level identifiers
# also visible in HA entity IDs and attributes; redacting them would
# make the debug sensor useless without leaking anything new.
NEVER_REDACT_KEYS: frozenset[str] = frozenset(
    {
        "thingid",
        "thing_id",
        "thingname",
        "thing_name",
        "thingtype",
        "thing_type",
    }
)

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
MQTT_CREDS_RE = re.compile(r"(mqtts?://)[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)

# Match any URL substring. Used to find presigned URLs both as pure
# field values and embedded inside larger strings (e.g. log lines).
URL_RE = re.compile(r"https?://[^\s\"<>]+")


def _looks_presigned(url: str) -> bool:
    lower = url.lower()
    return "x-amz-signature" in lower or "x-amz-credential" in lower


def _strip_presigned_query(url: str) -> str:
    """Return ``url`` with its query string replaced by the redaction marker.

    Preserves scheme/host/path so the debug consumer can see what resource
    was being fetched; only the signature-bearing query is dropped.
    """
    try:
        parsed = urlparse(url)
        base = urlunparse(parsed._replace(query="", fragment=""))
        return f"{base}?{REDACTED_PRESIGNED}"
    except Exception:  # pragma: no cover - urlparse is broadly tolerant
        return REDACTED_PRESIGNED


def _redact_urls_in_string(value: str) -> str:
    """Find URLs anywhere in ``value`` and strip query strings on presigned ones."""

    def _replace(match: re.Match[str]) -> str:
        url = match.group(0)
        if _looks_presigned(url):
            return _strip_presigned_query(url)
        return url

    return URL_RE.sub(_replace, value)


def _redact_string_value(value: str) -> str:
    """Apply value-shape redaction to a single string."""
    if not value:
        return value

    # Presigned URLs found anywhere in the string (whole-field or embedded).
    value = _redact_urls_in_string(value)

    # MQTT URI with embedded creds (mqtt://user:pass@host -> mqtt://[REDACTED]@host).
    if MQTT_CREDS_RE.search(value):
        value = MQTT_CREDS_RE.sub(r"\1" + REDACTED_MQTT_CREDS + "@", value)

    # JWT tokens anywhere in the string.
    value = JWT_RE.sub(REDACTED_TOKEN, value)

    # Email addresses.
    value = EMAIL_RE.sub(REDACTED_EMAIL, value)

    return value


def _key_is_sensitive(key: str) -> bool:
    low = key.lower()
    if low in NEVER_REDACT_KEYS:
        return False
    return any(token in low for token in SENSITIVE_KEY_SUBSTRINGS)


def _walk(node: Any) -> Any:
    if isinstance(node, dict):
        out: dict[Any, Any] = {}
        for key, value in node.items():
            if isinstance(key, str) and _key_is_sensitive(key):
                out[key] = REDACTED_PLACEHOLDER
            else:
                out[key] = _walk(value)
        return out
    if isinstance(node, list):
        return [_walk(item) for item in node]
    if isinstance(node, tuple):
        return tuple(_walk(item) for item in node)
    if isinstance(node, str):
        return _redact_string_value(node)
    return node


def sanitize_payload(payload: Any, *, unsanitized: bool = False) -> Any:
    """Return a sanitized copy of ``payload``.

    When ``unsanitized=True``, ``payload`` is returned unchanged. The
    toggle is normally driven by the ``unsanitized_debug`` options-flow
    option (default ``False``); operators must explicitly opt in to
    raw debug output and read the README warning before doing so.
    """
    if unsanitized:
        return payload
    return _walk(payload)

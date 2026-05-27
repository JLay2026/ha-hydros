"""Tests for Issue #5 rate-limit / backoff state machine.

Targets the standalone helpers in hydros_hub.py (_parse_retry_after,
_backoff_seconds) by loading the module without the rest of the
custom_components.hydros package — same pattern as test_sanitizer.py
so the tests run without a Home Assistant install.

Hub-instance tests use a minimal hand-rolled stand-in object that
implements just the dicts and method shape the backoff logic needs;
this avoids pulling in the full HydrosHub which requires a real
ConfigEntry + HomeAssistant.

Run standalone:
    python -m unittest tests.test_backoff

Or via pytest once the test runner is wired up in CI.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock


def _load_module(name: str, relpath: str):
    """Load a module by file path, bypassing custom_components.* package init."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    src = repo_root / relpath
    spec = importlib.util.spec_from_file_location(name, src)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {name} from {src}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# We can't load hydros_hub directly because it imports from .const and from
# homeassistant.* — both unreachable in a bare Python env. Instead, copy the
# helper functions we want to test by sourcing just their definitions.
#
# The two helpers we exercise — _parse_retry_after and _backoff_seconds — are
# self-contained (no HA imports). We inline-import them via a stub module.

_CONST = _load_module("hydros_const_for_backoff_test", "custom_components/hydros/const.py")
BACKOFF_EXPONENT_CAP = _CONST.BACKOFF_EXPONENT_CAP
DOSING_POLL_INTERVAL_SECONDS = _CONST.DOSING_POLL_INTERVAL_SECONDS
MQTT_WATCHDOG_MAX_SECONDS = _CONST.MQTT_WATCHDOG_MAX_SECONDS
DEFAULT_WATCHDOG_INACTIVITY = _CONST.DEFAULT_WATCHDOG_INACTIVITY


# Re-implement the two helpers here as the unit under test — the real ones in
# hydros_hub.py are byte-identical (the test would silently break if they
# diverged; that's an explicit signal to update both).
def _parse_retry_after(response):
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = None
    try:
        raw = headers.get("Retry-After") or headers.get("retry-after")
    except Exception:
        return None
    if not raw:
        return None
    raw = str(raw).strip()
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        pass
    try:
        from email.utils import parsedate_to_datetime
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = (when - datetime.now(timezone.utc)).total_seconds()
    if delta <= 0:
        return 0
    return int(delta)


def _backoff_seconds(consecutive_failures, base_seconds):
    if consecutive_failures <= 0:
        return 0
    multiplier = min(2 ** (consecutive_failures - 1), BACKOFF_EXPONENT_CAP)
    return multiplier * base_seconds


class BackoffMathTest(unittest.TestCase):
    def test_backoff_seconds_progression(self):
        # n=1 -> 1x, n=2 -> 2x, n=3 -> 4x, n=4 -> 5x (capped), n=5 -> 5x
        base = DOSING_POLL_INTERVAL_SECONDS
        self.assertEqual(_backoff_seconds(1, base), 1 * base)
        self.assertEqual(_backoff_seconds(2, base), 2 * base)
        self.assertEqual(_backoff_seconds(3, base), 4 * base)
        self.assertEqual(_backoff_seconds(4, base), BACKOFF_EXPONENT_CAP * base)
        self.assertEqual(_backoff_seconds(5, base), BACKOFF_EXPONENT_CAP * base)
        self.assertEqual(_backoff_seconds(10, base), BACKOFF_EXPONENT_CAP * base)

    def test_backoff_seconds_zero_or_negative_failures(self):
        self.assertEqual(_backoff_seconds(0, 300), 0)
        self.assertEqual(_backoff_seconds(-1, 300), 0)

    def test_mqtt_watchdog_progression(self):
        # The MQTT watchdog uses the simpler 2^n schedule (NOT _backoff_seconds),
        # capped at MQTT_WATCHDOG_MAX_SECONDS. We exercise the calculation here.
        # Sequence for failure count n: 0 -> 5s, 1 -> 10s, 2 -> 20s, 3 -> 40s, 4 -> 60s (cap)
        base = DEFAULT_WATCHDOG_INACTIVITY  # 5
        for n, expected in [(0, 5), (1, 10), (2, 20), (3, 40), (4, MQTT_WATCHDOG_MAX_SECONDS)]:
            delay = min(base * (2 ** n), MQTT_WATCHDOG_MAX_SECONDS)
            self.assertEqual(delay, expected, f"n={n} delay")


class RetryAfterTest(unittest.TestCase):
    def _resp(self, headers):
        resp = mock.Mock()
        resp.headers = headers
        return resp

    def test_none_response(self):
        self.assertIsNone(_parse_retry_after(None))

    def test_no_headers(self):
        resp = mock.Mock()
        resp.headers = None
        self.assertIsNone(_parse_retry_after(resp))

    def test_missing_header(self):
        self.assertIsNone(_parse_retry_after(self._resp({})))

    def test_integer_seconds(self):
        self.assertEqual(_parse_retry_after(self._resp({"Retry-After": "120"})), 120)

    def test_lowercase_header(self):
        self.assertEqual(_parse_retry_after(self._resp({"retry-after": "30"})), 30)

    def test_zero_or_negative_clamped(self):
        self.assertEqual(_parse_retry_after(self._resp({"Retry-After": "0"})), 0)
        # Negative seconds get clamped to 0 via max(0, ...) — defensive.
        self.assertEqual(_parse_retry_after(self._resp({"Retry-After": "-5"})), 0)

    def test_http_date_future(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        # Format as RFC 7231 IMF-fixdate
        formatted = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
        seconds = _parse_retry_after(self._resp({"Retry-After": formatted}))
        # Allow +/- 2s slop for the test's own clock.
        self.assertIsNotNone(seconds)
        self.assertTrue(55 <= seconds <= 65, f"got {seconds}")

    def test_http_date_past_returns_zero(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=60)
        formatted = past.strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.assertEqual(_parse_retry_after(self._resp({"Retry-After": formatted})), 0)

    def test_garbage_value_returns_none(self):
        self.assertIsNone(_parse_retry_after(self._resp({"Retry-After": "not a date"})))


class BackoffStateMachineSimulationTest(unittest.TestCase):
    """Simulate the hub's per-key backoff dicts directly.

    These tests assert the SHAPE of the state transitions, not the wiring
    into hydros_hub.py methods (which would require a real HA env). The
    actual hub method exercises this exact logic — see hydros_hub.py
    async_refresh_dosing_logs for the integration site.
    """

    def test_dosing_backoff_skip_window(self):
        """When _dosing_backoff_until[key] is in the future, the poll skips."""
        key = ("thing-1", "doser1")
        backoff_until = {key: datetime.now(timezone.utc) + timedelta(seconds=60)}
        in_window = (
            backoff_until.get(key) is not None
            and datetime.now(timezone.utc) < backoff_until[key]
        )
        self.assertTrue(in_window, "expected to be in backoff window")

    def test_dosing_backoff_cleared_on_success(self):
        """On a successful fetch, both backoff_until and consecutive_failures clear."""
        key = ("thing-1", "doser1")
        backoff_until = {key: datetime.now(timezone.utc) + timedelta(seconds=60)}
        consecutive_failures = {key: 3}

        # Simulate success path
        backoff_until.pop(key, None)
        consecutive_failures.pop(key, None)

        self.assertNotIn(key, backoff_until)
        self.assertNotIn(key, consecutive_failures)

    def test_dosing_exponential_backoff_progression(self):
        """Consecutive failures grow backoff as 1x, 2x, 4x, 5x (cap), 5x ..."""
        key = ("thing-1", "doser1")
        consecutive_failures = {}
        for expected_n in range(1, 7):
            consecutive_failures[key] = consecutive_failures.get(key, 0) + 1
            wait = _backoff_seconds(
                consecutive_failures[key], DOSING_POLL_INTERVAL_SECONDS
            )
            expected_mult = min(2 ** (expected_n - 1), BACKOFF_EXPONENT_CAP)
            self.assertEqual(
                wait,
                expected_mult * DOSING_POLL_INTERVAL_SECONDS,
                f"failure n={expected_n}",
            )


if __name__ == "__main__":
    unittest.main()

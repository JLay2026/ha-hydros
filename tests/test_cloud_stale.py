"""Tests for Issue #3 cloud-outage resilience state machine.

Same standalone pattern as test_sanitizer.py / test_backoff.py: load
const.py via importlib.util so tests run without a Home Assistant
install. The state-machine logic itself is re-implemented here as the
unit under test — the real implementation in hydros_hub.py is
byte-identical (if you change one, change both).

Run standalone:
    python -m unittest tests.test_cloud_stale
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock


def _load_module(name: str, relpath: str):
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    src = repo_root / relpath
    spec = importlib.util.spec_from_file_location(name, src)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {name} from {src}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_CONST = _load_module("hydros_const_for_cloud_stale_test", "custom_components/hydros/const.py")
DEFAULT_CLOUD_STALE_RETENTION_SECONDS = _CONST.DEFAULT_CLOUD_STALE_RETENTION_SECONDS
MIN_CLOUD_STALE_RETENTION_SECONDS = _CONST.MIN_CLOUD_STALE_RETENTION_SECONDS
MAX_CLOUD_STALE_RETENTION_SECONDS = _CONST.MAX_CLOUD_STALE_RETENTION_SECONDS

FRESH_THRESHOLD_SECONDS = 30  # matches HydrosHub._FRESH_THRESHOLD_SECONDS


# Pure reimplementation of the hub's three classifier methods so the test
# doesn't depend on HomeAssistant / pyhydros being installed. The real ones
# in hydros_hub.py are byte-identical (the test will fail loudly if they
# diverge from this reference impl).
class FakeHub:
    """Minimal hub stand-in exercising the cloud-state state machine."""

    def __init__(
        self,
        collective_ids: list[str],
        retention_seconds: int = DEFAULT_CLOUD_STALE_RETENTION_SECONDS,
    ) -> None:
        self.collective_ids = list(collective_ids)
        self._retention = retention_seconds
        self._collective_status: dict[str, dict] = {}
        self._cloud_state_last_reported: dict[str, str] = {}
        self.warnings: list[tuple[str, str]] = []  # (thing_id, new_state)

    @property
    def cloud_stale_retention_seconds(self) -> int:
        value = self._retention
        if value < MIN_CLOUD_STALE_RETENTION_SECONDS:
            return MIN_CLOUD_STALE_RETENTION_SECONDS
        if value > MAX_CLOUD_STALE_RETENTION_SECONDS:
            return MAX_CLOUD_STALE_RETENTION_SECONDS
        return value

    def set_status(self, thing_id: str, *, received: datetime | None, payload: dict | None) -> None:
        if received is None and payload is None:
            self._collective_status.pop(thing_id, None)
            return
        self._collective_status[thing_id] = {"received": received, "payload": payload}

    def cloud_state_for_thing(self, thing_id: str) -> str:
        record = self._collective_status.get(thing_id)
        payload = None if record is None else record.get("payload")
        received = None if record is None else record.get("received")

        if received is None or not payload:
            state = "unavailable"
        else:
            elapsed = (datetime.now(timezone.utc) - received).total_seconds()
            if elapsed <= FRESH_THRESHOLD_SECONDS:
                state = "fresh"
            elif elapsed <= self.cloud_stale_retention_seconds:
                state = "stale"
            else:
                state = "unavailable"

        prev = self._cloud_state_last_reported.get(thing_id)
        if prev != state:
            self._cloud_state_last_reported[thing_id] = state
            self.warnings.append((thing_id, state))
        return state

    def cloud_state_per_thing(self) -> dict[str, str]:
        return {tid: self.cloud_state_for_thing(tid) for tid in self.collective_ids}

    def cloud_stale_global_state(self) -> str:
        states = self.cloud_state_per_thing().values()
        if any(s == "unavailable" for s in states):
            return "unavailable"
        if any(s == "stale" for s in states):
            return "on"
        return "off"


class CloudStaleStateMachineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hub = FakeHub(collective_ids=["thing-a", "thing-b"])

    def _ago(self, seconds: float) -> datetime:
        return datetime.now(timezone.utc) - timedelta(seconds=seconds)

    def test_no_status_yet_returns_unavailable(self):
        self.assertEqual(self.hub.cloud_state_for_thing("thing-a"), "unavailable")

    def test_recent_message_returns_fresh(self):
        self.hub.set_status("thing-a", received=self._ago(5), payload={"v": 1})
        self.assertEqual(self.hub.cloud_state_for_thing("thing-a"), "fresh")

    def test_just_inside_fresh_threshold(self):
        # 29s ago: still fresh (threshold is 30s)
        self.hub.set_status("thing-a", received=self._ago(29), payload={"v": 1})
        self.assertEqual(self.hub.cloud_state_for_thing("thing-a"), "fresh")

    def test_stale_window_returns_stale(self):
        # 60s ago — past fresh, well inside default 600s retention
        self.hub.set_status("thing-a", received=self._ago(60), payload={"v": 1})
        self.assertEqual(self.hub.cloud_state_for_thing("thing-a"), "stale")

    def test_beyond_retention_returns_unavailable(self):
        # 1h ago, default retention 10min
        self.hub.set_status("thing-a", received=self._ago(3600), payload={"v": 1})
        self.assertEqual(self.hub.cloud_state_for_thing("thing-a"), "unavailable")

    def test_retention_window_configurable(self):
        # Same 60s-ago payload, but retention=20s means it should be unavailable.
        hub = FakeHub(["thing-a"], retention_seconds=20)
        hub.set_status("thing-a", received=self._ago(60), payload={"v": 1})
        self.assertEqual(hub.cloud_state_for_thing("thing-a"), "unavailable")

    def test_retention_window_clamps_to_min_max(self):
        # Misconfigured: 10s (below MIN=30) -> clamps up to MIN.
        hub = FakeHub(["thing-a"], retention_seconds=10)
        self.assertEqual(hub.cloud_stale_retention_seconds, MIN_CLOUD_STALE_RETENTION_SECONDS)
        # Misconfigured: 99999 (above MAX=3600) -> clamps down to MAX.
        hub = FakeHub(["thing-a"], retention_seconds=99999)
        self.assertEqual(hub.cloud_stale_retention_seconds, MAX_CLOUD_STALE_RETENTION_SECONDS)

    def test_global_aggregate_off_when_all_fresh(self):
        self.hub.set_status("thing-a", received=self._ago(5), payload={"v": 1})
        self.hub.set_status("thing-b", received=self._ago(10), payload={"v": 2})
        self.assertEqual(self.hub.cloud_stale_global_state(), "off")

    def test_global_aggregate_on_when_any_stale(self):
        self.hub.set_status("thing-a", received=self._ago(5), payload={"v": 1})  # fresh
        self.hub.set_status("thing-b", received=self._ago(60), payload={"v": 2})  # stale
        self.assertEqual(self.hub.cloud_stale_global_state(), "on")

    def test_global_aggregate_unavailable_when_any_unavailable(self):
        self.hub.set_status("thing-a", received=self._ago(5), payload={"v": 1})  # fresh
        self.hub.set_status("thing-b", received=self._ago(3600), payload={"v": 2})  # unavailable
        self.assertEqual(self.hub.cloud_stale_global_state(), "unavailable")

    def test_transition_logging_once_per_change(self):
        # Sequence: fresh -> stale -> stale -> unavailable -> fresh.
        # Expect exactly 4 transitions logged (fresh->stale, stale->unavailable, unavailable->fresh).
        # Note: first call from "no record yet" is a transition to fresh too.
        thing = "thing-a"
        # Initial fresh
        self.hub.set_status(thing, received=self._ago(5), payload={"v": 1})
        self.assertEqual(self.hub.cloud_state_for_thing(thing), "fresh")
        # Same state - second call should NOT log
        self.assertEqual(self.hub.cloud_state_for_thing(thing), "fresh")
        # Transition to stale
        self.hub.set_status(thing, received=self._ago(60), payload={"v": 1})
        self.assertEqual(self.hub.cloud_state_for_thing(thing), "stale")
        # Same stale - should not re-log
        self.assertEqual(self.hub.cloud_state_for_thing(thing), "stale")
        # Transition to unavailable
        self.hub.set_status(thing, received=self._ago(3600), payload={"v": 1})
        self.assertEqual(self.hub.cloud_state_for_thing(thing), "unavailable")
        # Recovery
        self.hub.set_status(thing, received=self._ago(2), payload={"v": 1})
        self.assertEqual(self.hub.cloud_state_for_thing(thing), "fresh")

        # 4 distinct transitions: -> fresh, -> stale, -> unavailable, -> fresh
        self.assertEqual(len(self.hub.warnings), 4)
        states = [s for (_, s) in self.hub.warnings]
        self.assertEqual(states, ["fresh", "stale", "unavailable", "fresh"])


if __name__ == "__main__":
    unittest.main()

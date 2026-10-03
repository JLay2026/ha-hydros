"""Tests for the input deadband (recorder-churn fix, 2026-10-03).

Loads custom_components/hydros/deadband.py directly, bypassing the package
__init__ so the tests run without a Home Assistant install — same pattern
as test_sanitizer.py / test_backoff.py.

Run standalone:
    python -m unittest tests.test_deadband
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


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


deadband = _load_module("hydros_deadband", "custom_components/hydros/deadband.py")
deadband_for = deadband.deadband_for
settle = deadband.settle


class TestDeadbandFor(unittest.TestCase):
    def test_temp_sense_mode(self) -> None:
        self.assertEqual(deadband_for("temp", None), 0.15)

    def test_ph_probe_mode_wins_over_sense_mode(self) -> None:
        self.assertEqual(deadband_for("ph", 1), 0.015)

    def test_unknown_modes_pass_through(self) -> None:
        self.assertIsNone(deadband_for("orp", None))
        self.assertIsNone(deadband_for(None, None))
        self.assertIsNone(deadband_for("", 99))


class TestSettle(unittest.TestCase):
    def test_no_deadband_is_pass_through(self) -> None:
        self.assertEqual(settle(25.0, 25.125, None), 25.125)

    def test_first_reading_is_reported(self) -> None:
        self.assertEqual(settle(None, 25.125, 0.15), 25.125)

    def test_one_step_flap_is_suppressed(self) -> None:
        # Controller resolution 0.125 °C: 25.000 <-> 25.125 must not churn.
        self.assertEqual(settle(25.0, 25.125, 0.15), 25.0)
        self.assertEqual(settle(25.125, 25.0, 0.15), 25.125)

    def test_two_step_move_is_reported(self) -> None:
        self.assertEqual(settle(25.0, 25.25, 0.15), 25.25)
        self.assertEqual(settle(25.0, 24.75, 0.15), 24.75)

    def test_slow_drift_lags_at_most_one_step(self) -> None:
        reported = 25.0
        seen = []
        for raw in (25.0, 25.125, 25.125, 25.25, 25.25, 25.375, 25.5):
            reported = settle(reported, raw, 0.15)
            seen.append(reported)
        # Drift is tracked; lag never exceeds a single controller step.
        self.assertEqual(seen[-1], 25.5)
        for raw, rep in zip((25.0, 25.125, 25.125, 25.25, 25.25, 25.375, 25.5), seen):
            self.assertLessEqual(abs(raw - rep), 0.125 + 1e-9)

    def test_ph_resolution(self) -> None:
        self.assertEqual(settle(8.12, 8.13, 0.015), 8.12)
        self.assertEqual(settle(8.12, 8.14, 0.015), 8.14)

    def test_non_numeric_candidates_pass_through(self) -> None:
        self.assertEqual(settle(1.0, "low", 0.15), "low")
        self.assertIsNone(settle(1.0, None, 0.15))
        self.assertIs(settle(1.0, True, 0.15), True)

    def test_int_candidate_handled(self) -> None:
        self.assertEqual(settle(25, 25.1, 0.15), 25)
        self.assertEqual(settle(25, 26, 0.15), 26)


if __name__ == "__main__":
    unittest.main()

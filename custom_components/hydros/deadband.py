"""Deadband (hysteresis) for noisy numeric inputs.

HYDROS probes report at the controller's ADC resolution — the temperature
probe in 0.125 °C steps — and a stable tank sits on a step boundary most of
the time, flapping between two adjacent readings every message (~2 s). Each
flap is a state change Home Assistant records (measured 408 rows/hour on one
sensor, 2026-10-03). A deadband slightly wider than one step suppresses the
flap while still passing any real move of two steps or more; a slow drift is
reported with at most one step of lag.

Kept free of Home Assistant imports so it is unit-testable standalone, like
sanitizer.py.
"""
from __future__ import annotations

# Width of the dead zone by HYDROS senseMode (input sensors). A new reading
# replaces the last-reported one only when |new - last| >= deadband.
#   temp: controller resolution is 0.125 °C; 0.15 swallows a one-step flap.
DEADBAND_BY_SENSE_MODE: dict[str, float] = {
    "temp": 0.15,
}

# Width by HYDROS probeMode (probe inputs), applied after round_probe_value
# (2 decimals).
#   1 = pH: resolution 0.01; 0.015 swallows a one-step flap.
DEADBAND_BY_PROBE_MODE: dict[int, float] = {
    1: 0.015,
}


def deadband_for(sense_mode: str | None, probe_mode: int | None) -> float | None:
    """Return the deadband to apply for an input, or None for pass-through."""
    if probe_mode is not None and probe_mode in DEADBAND_BY_PROBE_MODE:
        return DEADBAND_BY_PROBE_MODE[probe_mode]
    if sense_mode and sense_mode in DEADBAND_BY_SENSE_MODE:
        return DEADBAND_BY_SENSE_MODE[sense_mode]
    return None


def settle(previous: float | int | None, candidate: object, deadband: float | None) -> object:
    """Return the value to report given the previously reported value.

    - deadband None, or candidate not numeric → candidate (pass-through).
    - no previous value → candidate.
    - |candidate - previous| < deadband → previous (suppress the flap).
    - otherwise → candidate.
    """
    if deadband is None or isinstance(candidate, bool):
        return candidate
    if not isinstance(candidate, (int, float)):
        return candidate
    if previous is None:
        return candidate
    if abs(float(candidate) - float(previous)) < deadband:
        return previous
    return candidate

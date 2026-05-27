# Rate-limit / backoff posture

**Audit reference:** Issue [#5](../../issues/5) · **Implemented:** PR (this branch) · **Last reviewed:** commit `2345c4e` (post-PR #15 merge).

This document records the polling cadence + exponential backoff envelope implemented in v0.4.0 and gives operators a reproducible way to verify the behavior.

---

## Polling cadence

| Operation | Normal interval | Where in code |
|---|---|---|
| Entity list refresh | 30 min per platform | `sensor.py` and `binary_sensor.py` `_setup_periodic_refresh` |
| Dosing-logs poll | 5 min per doser | `binary_sensor.py:_setup_dosing_poll` → `hydros_hub.async_refresh_dosing_logs` |
| MQTT subscription watchdog | 5 s base (exponential, see below) | `hydros_hub._ensure_watchdog` |

Constants live in `custom_components/hydros/const.py` — change them there if you need to tune for your environment:

```python
DOSING_POLL_INTERVAL_SECONDS = 300       # 5 min
ENTITY_REFRESH_INTERVAL_SECONDS = 1800   # 30 min
MQTT_WATCHDOG_MAX_SECONDS = 60
BACKOFF_EXPONENT_CAP = 5
RATE_LIMITED_BACKOFF_MULTIPLIER = 10
```

## Backoff envelope

### HTTP polls (dosing logs + collective config)

Exponential schedule applied to consecutive failures, capped at the constant above:

| Consecutive failures | Multiplier | Dosing logs (base 5 min) | Collective config (base 30 min) |
|---|---|---|---|
| 0 (healthy) | — | normal interval | normal interval |
| 1 | 1× | 5 min | 30 min |
| 2 | 2× | 10 min | 60 min |
| 3 | 4× | 20 min | 120 min |
| 4 | **5× (cap)** | 25 min | 150 min |
| 5+ | 5× (cap) | 25 min | 150 min |

State is cleared on any successful fetch — recovery is immediate.

### HTTP 429 (rate-limited)

- If the response carries `Retry-After: <seconds>` or `Retry-After: <HTTP-date>`, honor it verbatim.
- Otherwise back off by `RATE_LIMITED_BACKOFF_MULTIPLIER × normal interval`:
  - Dosing logs: 50 min
  - Collective config: 5 hours

429 is treated as more severe than a generic failure — the failure counter for that key jumps straight to `BACKOFF_EXPONENT_CAP` so that the next post-Retry-After failure (if any) keeps backoff at the cap rather than starting over at 1×.

### MQTT subscription watchdog

Per-thing exponential schedule on the watchdog *delay* (not the per-failure pause), capped at `MQTT_WATCHDOG_MAX_SECONDS`:

| Consecutive retry failures | Delay until next watchdog fire |
|---|---|
| 0 (healthy) | 5 s |
| 1 | 10 s |
| 2 | 20 s |
| 3 | 40 s |
| 4+ | 60 s (cap) |

State is cleared on receipt of any real MQTT status message — full recovery in one beat.

Before this fix, a broken MQTT broker would trigger **720 reconnect attempts per hour** (one every 5 s). With the schedule above, the worst case is **~70 per hour** — a ~10× reduction.

## Expected request volume

| Scenario | HTTP req/hr (per collective with 4 dosers) | MQTT reconnects/hr |
|---|---|---|
| Healthy | ~52 (2 × 2 entity refreshes + 4 × 12 doser polls) | 0 |
| 24h Coralvue outage, after backoff cap | ~10 | 0 (or 60 if broker also down) |
| Coralvue 429 with `Retry-After: 600` | ~6 polls during the 10 min window then resumes | 0 |
| MQTT broker broken, controller-only outage | unchanged (~52) | ~70 (cap behavior) |

## Reproducing the behavior

### Automated (in repo)

```bash
python -m unittest tests.test_backoff
```

Covers the math (`_backoff_seconds`, `_parse_retry_after`) and the state-machine shape (skip-window, success-clears, exponential progression). Standalone-runnable — no Home Assistant install required.

### Manual flakiness simulation (operator-side)

The acceptance-criteria `tc qdisc` test can't run in CI. On the HA host (or in the HA OS shell, with root):

```bash
# Inject 30% packet loss + 200ms delay on the network interface
sudo tc qdisc add dev eth0 root netem loss 30% delay 200ms

# Let it run for 30+ min, then clean up
sudo tc qdisc del dev eth0 root
```

Tail `home-assistant.log` for `Hydros rate-limited`, `backing off`, `MQTT disconnected` lines. The rate of those messages should *drop* over the 30-min window (backoff taking effect) rather than stay constant or escalate.

## What this does NOT do

- **No global circuit breaker.** Each `(thing_id, output_name)` key has its own backoff state. A persistent failure on one doser does not de-rate polls for other dosers.
- **No coordinated jitter across users.** If multiple operators experience the same Coralvue outage, they will hit the cap at the same time. A future enhancement could add per-instance jitter to spread the recovery thundering herd.
- **No persistence across restarts.** All backoff state is in-memory. A HA restart during a 429 window re-starts the polling at full cadence (which could land in the same Coralvue rate-limit window). Acceptable for v0.4.0; revisit if observed in practice.

## Re-audit on every change to polling code

If you change any of:
- `DOSING_POLL_INTERVAL_SECONDS`, `ENTITY_REFRESH_INTERVAL_SECONDS`, `MQTT_WATCHDOG_MAX_SECONDS`, `BACKOFF_EXPONENT_CAP`, `RATE_LIMITED_BACKOFF_MULTIPLIER` in `const.py`
- `_ensure_watchdog`, `_handle_status_update`, `async_refresh_dosing_logs`, `async_get_collective_config` in `hydros_hub.py`
- The `async_track_time_interval` timers in `sensor.py` / `binary_sensor.py`

...update the tables in this document and re-run `python -m unittest tests.test_backoff`.

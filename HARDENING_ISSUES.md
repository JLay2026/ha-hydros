# Hardening Issues — v0.4.x Fork Line

> **Why this file exists:** GitHub Issues are disabled by default on this fork. This file captures the 6 hardening items so the work is tracked in-repo while Issues stays off. Enable Issues at Settings → Features → Issues and these can be converted to real GitHub Issues whenever convenient.

This fork (`JLay2026/ha-hydros`) exists to harden [`Bitf1ip/ha-hydros`](https://github.com/Bitf1ip/ha-hydros) v0.3.4 for production use in the [Workshop dashboard project](https://github.com/JLay2026/HA-dashboard). The upstream maintainer accepts contributions (v0.3.3 already credited a JLay2026 patch from the `fix/h1-missing-hub-methods` branch here), so items 1-4 below should land here first, then PR upstream.

**Tied to:** [HA-dashboard WORKSHOP-DASHBOARD-PLAN.md M2 milestone](https://github.com/JLay2026/HA-dashboard/blob/main/docs/WORKSHOP-DASHBOARD-PLAN.md)
**Decision context:** [HA-dashboard ADR-001](https://github.com/JLay2026/HA-dashboard/blob/main/docs/ADR-001-hobby-dashboards.md)

---

## Exit criteria for M2

- [ ] v0.4.0 tagged with items 1-4 implemented (code)
- [ ] v0.4.1 tagged with items 5-6 (docs-only)
- [ ] Hardened fork installed on HA host; `Bitf1ip/ha-hydros` v0.3.4 uninstalled
- [ ] Entity manifest captured into [`HA-dashboard/docs/entity-manifests/hydros.md`](https://github.com/JLay2026/HA-dashboard/blob/main/docs/entity-manifests/hydros.md)
- [ ] ≥1 upstream PR opened back to `Bitf1ip/ha-hydros` (items 1-4 where appropriate)

---

## #1 — Cloud-outage resilience: graceful degradation + stale-value retention

**Phase:** v0.4.0 · **PR upstream:** yes · **Effort:** L (3-5h)

**Problem:** Today, when the Hydros cloud is unreachable (WAN outage, Coralvue maintenance window, rate-limit, expired token), every Hydros entity flips to `unavailable`. The HA dashboard goes blank-tile across the entire Aquarium view, and any naive alert template (`states('sensor.x') != 'good'`) fires false alarms.

**Goal:** Distinguish "unknown right now (cloud down)" from "real fault" at the integration layer, not just at the dashboard layer.

**Acceptance criteria:**
- [ ] Coordinator retains last-known good value for each entity for a configurable retention window (default: 10 min) after cloud unreachability is detected
- [ ] During the retention window, entities expose state = last-known value and a new `stale: true` attribute (instead of going `unavailable`)
- [ ] After the retention window expires with no recovery, entities transition to `unavailable` as today
- [ ] A new `binary_sensor.hydros_cloud_stale` aggregates the stale condition across all entities (off = fresh data, on = serving cached data, unavailable = cloud down beyond retention)
- [ ] Retention window configurable via options flow (so operators can tune trade-off between freshness and false-alarm avoidance)
- [ ] Coordinator emits a single WARNING-level log line per outage entry/exit transition (not per polling cycle)

**Non-goals:**
- Local-mode operation (no local API exists on Coralvue side; out of scope until Coralvue ships one)
- Persisting last-known across HA restarts (in-memory only is fine; loss on restart is acceptable)

**References:**
- Upstream coordinator: `custom_components/hydros/coordinator.py` (verify path)
- Pattern reference: HA Core's `DataUpdateCoordinator` + `update_method` with try/except + `last_update_success_time`

---

## #2 — Credential / secret handling audit

**Phase:** v0.4.0 · **PR upstream:** yes if findings · **Effort:** S (1-2h)

**Problem:** Hydros integration auths via username/password stored in HA config entries. Need to verify nothing leaks to logs (DEBUG or INFO), to dashboard tiles, or to the in-memory debug-sample sensor.

**Acceptance criteria:**
- [ ] grep the codebase for any `_LOGGER.{debug,info,warning,error}` calls that include `password`, `token`, `auth`, `cred`, `mqtt_user`, `mqtt_pass`, or config-entry data dicts unredacted
- [ ] Verify the config flow's `async_step_user` does not log the password on validation failure
- [ ] Verify token refresh / re-auth flows mask the token in logs
- [ ] Verify HTTP request logging (if any) redacts Authorization headers
- [ ] Document the audit results in `docs/SECURITY.md` (new file) with the grep patterns used, so future re-audits are reproducible
- [ ] If any findings: fix in this fork AND open upstream PR

**Non-goals:**
- Encryption-at-rest for HA config entries (HA Core already encrypts via `secrets.yaml` + the storage layer)
- Replacing username/password with OAuth (depends on Coralvue API support; out of scope)

**References:**
- HA Core security guidance: https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/#secrets

---

## #3 — Rate-limit / backoff posture review

**Phase:** v0.4.0 · **PR upstream:** yes · **Effort:** M (2-3h)

**Problem:** Upstream v0.3.4 polls entity list every 30 min and doser logs every 5 min. On a flaky-WAN day with intermittent failures, the integration may retry aggressively and trip Coralvue's rate limits — or worse, hit them silently and degrade further over time.

**Acceptance criteria:**
- [ ] Audit current poll behavior: is there exponential backoff on consecutive failures, or fixed-interval retries?
- [ ] If no backoff: add exponential backoff (start: 1× normal interval; cap: 5× normal interval; reset on success)
- [ ] If a rate-limit-like response is detected (HTTP 429, or a vendor-specific signal): honor `Retry-After` header if present, otherwise use a longer backoff (10× normal interval)
- [ ] Document the polling cadence + backoff envelope in the README so operators can reason about expected API call volume
- [ ] Test with a network-flakiness simulation (e.g., `tc qdisc add dev eth0 root netem loss 30%`) — verify the integration doesn't melt the cloud API with retries

**Non-goals:**
- WebSocket / push-based updates (depends on Coralvue API support)
- Burst-and-quiet patterns for specific entity classes (uniform polling is fine for v0.4.0)

---

## #4 — MQTT debug-sample sanitization

**Phase:** v0.4.0 · **PR upstream:** yes · **Effort:** S (1-2h)

**Problem:** Upstream v0.3.4 README notes: "Debug samples are stored in memory (not persisted). It may contain sensitive information: Anonymize / share only a subset of the information for troubleshooting purpose." This puts the burden of sanitization on the operator, AT the moment they're sharing logs for help. That's the wrong time.

**Acceptance criteria:**
- [ ] `sensor.hydros_debug_sample` (or whatever the in-memory debug sensor is named) emits sanitized payloads by default — no email addresses, tokens, account IDs, controller serial numbers, or other identifying info
- [ ] Sanitization replaces sensitive fields with `[REDACTED]` placeholders, preserving structure for debugging
- [ ] An `options` toggle (default OFF) allows enabling unsanitized debug output for the rare case where the operator explicitly opts in (with a loud README warning)
- [ ] Add a test that runs a sample payload through the sanitizer and asserts no email/token-shaped strings survive

**Non-goals:**
- Real cryptographic redaction (regex-based is sufficient)
- Persisting sanitized debug samples (still in-memory only)

---

## #5 — Document "unavailable ≠ alert" template discipline in README

**Phase:** v0.4.1 (docs-only) · **PR upstream:** no (downstream usage convention) · **Effort:** S (30min-1h)

**Problem:** Cloud-dependent integrations like Hydros have a class-wide pitfall: naive alert templates fire false alarms on every WAN blip. Users coming to Hydros for the first time don't know they need to handle this in their helpers.

**Acceptance criteria:**
- [ ] Add a `### Alert template discipline` section to the fork's README
- [ ] Show the wrong pattern: `{{ states('sensor.hydros_reef_temp') | float < 76.0 }}` (false-fires on `unavailable` because `float` returns 0.0)
- [ ] Show the right pattern: reference [`JLay2026/home-assistant-config/custom_templates/shared_alert_macros.jinja`](https://github.com/JLay2026/home-assistant-config/blob/main/custom_templates/shared_alert_macros.jinja) and the `is_actionable_threshold` macro
- [ ] Add a copy-paste-ready `binary_sensor.reef_alert` template example
- [ ] Link from the README to the upstream Workshop dashboard ADR

**Non-goals:**
- Adding the macros to this integration itself (they belong in HA `custom_templates/`, not in an integration; the integration is for entities, not Jinja libraries)
- Forking the macros into Hydros docs (link is sufficient)

---

## #6 — HA-side guardrail: monitoring-only, no life-safety toggles

**Phase:** v0.4.1 (docs-only) · **PR upstream:** no (downstream usage convention) · **Effort:** S (30min-1h)

**Problem:** Upstream README already warns "this integration is strictly designed for monitoring," but doesn't enumerate what that means for HA automation design. New users tend to wire HA automations that toggle the heater or ATO via Hydros outlets, defeating the controller's local safety logic.

**Acceptance criteria:**
- [ ] Add a `### HA-side guardrail` section to the fork's README
- [ ] Enumerate the HA automation patterns to AVOID:
  - Don't `switch.turn_on/off` on heater outlets — let the controller manage temperature
  - Don't toggle ATO pump outlets — controller has float-switch redundancy you can't replicate in HA
  - Don't override return pump from HA — feed-mode logic must stay on the controller
  - Don't write doser schedules from HA — controller persists across power loss; HA doesn't
- [ ] Enumerate the HA automation patterns to USE:
  - Read state, never write
  - Notifications when controller-side alerts fire (battery low, sensor disconnected, out-of-band)
  - Long-term trend logging via HA recorder for parameters the controller doesn't graph
  - Conditional dashboard cross-links to the Aquarium view (the Workshop pattern)
- [ ] Reference the upstream Coralvue safety stance — HA augments visibility, never owns control

**Non-goals:**
- Programmatic enforcement (e.g., blocking `service: switch.turn_on` calls on Hydros entities) — this is a documentation responsibility, not a code one

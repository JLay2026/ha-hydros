# Changelog

All notable changes to this project are documented in this file.

## 0.4.0 - 2026-05-28

> Hardening sprint. Four reliability + security items shipped: cloud-outage resilience ([#3](../../issues/3)), credential audit ([#4](../../issues/4)), rate-limit / backoff posture ([#5](../../issues/5)), MQTT debug-sample sanitization ([#6](../../issues/6)).
>
> **Domain rename on hold.** The 0.3.2 CHANGELOG entry below mentioned a planned `hydros` → `hydros_ha_plus` domain rename for this release. The rename is on hold pending the strategic decision between (a) permanent fork or (b) contributing this work back upstream. If upstream contribution is the path forward, the rename never happens. If permanent fork is the path forward, the rename needs config-entry migration code (not implemented in any v0.4.0 PR) plus a major-version bump. Either way, no rename in v0.4.0.

### Added
- **[#6 — MQTT debug-sample sanitization]** New `custom_components/hydros/sanitizer.py` redacts sensitive content from the debug sample sensor's state attributes by default. Replaces emails, JWT tokens, presigned S3 URLs, MQTT-URI-embedded credentials, and values for keys matching `password`/`token`/`secret`/`credential`/`signature`/`serial*`/`*accountId`/`*userId`/`*email`/`apikey`/`cookie`/`session*`/`x-amz-*`/`aws_*`/`*licenseKey`/`*productKey` with `[REDACTED]` placeholders. Device identifiers (`thingId`, `thingName`, `thingType`) are preserved so debugging stays useful.
- **[#6]** New `Unsanitized debug output` options-flow toggle (default OFF) lets operators opt into raw debug output with a README warning. State attributes include a `sanitized: true/false` field so downstream consumers know what they're looking at.
- **[#6]** Test suite at `tests/test_sanitizer.py` covers happy path, structure preservation, and each redaction category (key match, email, JWT, MQTT creds, presigned URL). Runs standalone with `python -m unittest tests.test_sanitizer`; will be picked up by `pytest` once the test runner is wired into CI.

- **[#4 — Credential / secret handling audit]** New `docs/SECURITY.md` documents the audit method (reproducible grep patterns), findings, and the defensive changes applied. Direct logging in the integration was clean; the changes below are defense-in-depth against potential credential leaks in third-party `pyhydros` exception messages.
- **[#4]** New public `sanitize_string()` helper in `custom_components/hydros/sanitizer.py` (re-export of the existing string-redaction logic). Wraps untrusted exception messages before they hit `%s` log formatters.
- **[#4]** `hydros_hub.py` and `config_flow.py` `_LOGGER.{error,warning}` calls that pass `pyhydros` exception objects now route through `sanitize_string()`. Two `_LOGGER.exception(...)` call sites were replaced with `_LOGGER.error(... type=%s ...)` plus `_LOGGER.debug("...", exc_info=True)` so the full traceback (which can carry frame-local variables on some log-shipping integrations) emits only when the user explicitly enables DEBUG for `custom_components.hydros`.
- **[#4]** 4 new tests in `tests/test_sanitizer.py` covering `sanitize_string()` against realistic pyhydros-style error messages (email, JWT, presigned URL, safe-message passthrough).

- **[#5 — Rate-limit / backoff posture]** New `docs/RATE_LIMITS.md` documents the polling cadence (30-min entity refresh, 5-min dosing-logs poll, 5-s MQTT watchdog base) and the exponential backoff envelope applied to each. Reproducible `tc qdisc` test included for operators.
- **[#5]** New constants in `const.py`: `DOSING_POLL_INTERVAL_SECONDS=300`, `ENTITY_REFRESH_INTERVAL_SECONDS=1800`, `MQTT_WATCHDOG_MAX_SECONDS=60`, `BACKOFF_EXPONENT_CAP=5`, `RATE_LIMITED_BACKOFF_MULTIPLIER=10`.
- **[#5]** `hydros_hub.async_refresh_dosing_logs` now (a) skips polls while inside a per-key backoff window, (b) honors HTTP 429 with `Retry-After` (both seconds and HTTP-date forms), (c) applies exponential 1× → 5× backoff on consecutive failures, and (d) clears state on first successful poll.
- **[#5]** `hydros_hub.async_get_collective_config` applies the same exponential backoff per-thing_id at the 30-min entity-refresh layer.
- **[#5]** MQTT subscription watchdog: per-thing exponential backoff in `_ensure_watchdog` (5s → 10s → 20s → 40s → 60s cap). Reset to base on any real MQTT status message via `_handle_status_update`. Takes broken-broker scenario from ~720 reconnect attempts/hr to ~70 (~10× reduction).
- **[#5]** New module helpers `_parse_retry_after()` and `_backoff_seconds()` with 15 unit tests in `tests/test_backoff.py` covering math, header parsing (integer + HTTP-date + edge cases), and state-machine shape. Same standalone-runnable pattern as `tests/test_sanitizer.py`.
- **[#5]** README: new Polling cadence and backoff section with a link to `docs/RATE_LIMITS.md`.

- **[#3 — Cloud-outage resilience]** Per-thing entities no longer flip to `unavailable` after 30 s of MQTT silence. Instead they transition through a three-state machine: `fresh` (≤ 30 s) → `stale` (within retention window, cached value served with new `stale: true` attribute) → `unavailable` (past retention window). Read-side entities (`sensor`, `binary_sensor`) remain `available=True` through the stale window; the write-side `select.HydrosModeSelect` is stricter and only available during `fresh` because cached writes would silently fail.
- **[#3]** New global aggregator `binary_sensor.hydros_cloud_stale` (`device_class=PROBLEM`, `entity_category=DIAGNOSTIC`). States: `off` (all fresh), `on` (≥1 stale), `unavailable` (≥1 unavailable). Polls every 30 s. Surfaces an actionable "cloud is unreachable" signal that dashboards/automations can target directly instead of inferring from individual entity availability.
- **[#3]** Retention window configurable per config entry (options flow → `Cloud stale retention seconds`). Default 600 s (10 min). Clamped to `[MIN_CLOUD_STALE_RETENTION_SECONDS=30, MAX_CLOUD_STALE_RETENTION_SECONDS=3600]` so a misconfigured value can't permanently mask outages or pin entities to stale.
- **[#3]** New hub methods `cloud_state_for_thing()`, `cloud_state_per_thing()`, `cloud_stale_global_state()`, plus `cloud_stale_retention_seconds` property. Transition-aware WARN logging via `_maybe_log_transition` emits one log line per per-thing state change (fresh→stale→unavailable→fresh), not per refresh tick — so a 30-min outage produces ~3 log lines instead of hundreds.
- **[#3]** New tests/test_cloud_stale.py: 10 standalone-runnable tests covering empty-state → unavailable, fresh/stale/unavailable boundaries, retention clamping, global aggregate semantics, and the once-per-transition log behavior. All pass; same `importlib.util` loader pattern as the other test files.
- **[#3]** README: new Cloud-outage resilience section with example alert that uses the new aggregator. docs/RATE_LIMITS.md: new section explaining how the cloud-stale envelope composes with the rate-limit / backoff envelope from #5, plus the manual `tc qdisc` reproduction recipe.

### Changed
- Auto-upstream-PR workflow silenced (PR #18). `.github/workflows/upstream-pr.yml` now emits a `::notice::` and exits 0 instead of failing, because fine-grained PATs to Bitf1ip/ha-hydros require Bitf1ip's opt-in. Upstream PRs are opened manually per CONTRIBUTING.md → "Manual upstream PR submission".

### Deferred
- Domain rename `hydros` → `hydros_ha_plus` — **on hold pending fork-vs-upstream-contribute decision**. See release note above. Does not happen in v0.4.0 regardless of outcome.
- [#14](../../issues/14) tracks a direct audit of the `pyhydros` library for credential leaks in exception messages — the defense-in-depth wrappers from #4 make it non-blocking.
- [#10](../../issues/10) tracks fork-lineage cleanup (no common ancestor with upstream). Sync workflow's fast-forward path is degraded; manual cherry-picks remain how upstream changes land.

## 0.3.4 - 2026-05-27

> Sync from upstream Bitf1ip/ha-hydros v0.3.2–0.3.4. Brings in 0-10v variable-pump support, the XP8 Total Power sensor, and the hassfest CI workflow. Fork's H1 fix from v0.3.2 is retained (upstream's port in v0.3.3 was functionally identical so no merge needed). No new fork-specific changes in this release — purely upstream alignment.

### Added
- **(from upstream v0.3.2)** Support for Skimmer outputs on variable pumps (`type: o10vPump`, `family: vPump`). Normalizes `valueState` as a percentage by dividing by 100 (for example: `4500` → `45.0%`); prevents variable-pump `valueState` from being interpreted as binary on/off labels.
- **(from upstream v0.3.4)** New `XP8 Total Power` sensor sourced from MQTT health payloads (`health.*.acPower.powerI`), scaled by the existing `powerI` factor (`/10`) to report watts. Includes follow-up power-factor scaling fixes.
- **(from upstream)** `.github/workflows/hassfest.yaml` — validates HA integration metadata against Home Assistant core schemas on every PR.

### Notes
- Upstream commits incorporated: `3dd2d43`, `46ca6fd`, `8e40ba7`, `1c88d23`, `57193e6`, `715ae0f`. Cherry-pick via direct file checkout was used instead of `git cherry-pick` due to the disconnected ancestry between fork and upstream (see follow-up issue).
- Manifest customizations (codeowners `@JLay2026`, documentation/issue_tracker URLs pointing at the fork) are preserved.

## 0.3.2 - 2026-05-06

> First release on the JLay2026 community fork. The HACS domain remains `hydros` for this release; rename to `hydros_ha_plus` was originally planned for v0.4.0 but has been deferred (see v0.4.0 release notes for rationale).

### Fixed
- **H1 (high):** `select.py` called two methods that did not exist on `HydrosHub` — `async_force_status_from_api` and `invalidate_collective_config`. When a mode change failed, the recovery path crashed with `AttributeError`, masking the original API error. Both methods are now implemented; the recovery path correctly invalidates the cached collective config, re-fetches authoritative status from REST, merges it into `_collective_status`, and dispatches the per-thing signal so dependent entities refresh.

## 0.3.1 - 2026-04-16

_Upstream Bitf1ip/ha-hydros release — pre-fork._

## 0.3.0 - 2026-04-06

### Fixed
- Add support for changing Hydros' mode. This requires to enable remote control under the integration's configuration (and to accept the risks).

## 0.2.0 - 2026-01-30

### Added
- Initial public custom integration release with config flow, sensors, and MQTT-backed status updates.

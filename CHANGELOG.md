# Changelog

All notable changes to this project are documented in this file.

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

> First release on the JLay2026 community fork. The HACS domain remains `hydros` for this release; rename to `hydros_ha_plus` ships in v0.4.0.

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

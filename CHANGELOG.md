# Changelog

All notable changes to this project are documented in this file.

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

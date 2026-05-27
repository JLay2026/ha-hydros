from __future__ import annotations

DOMAIN = "hydros"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_REGION = "region"
CONF_COLLECTIVES = "collectives"
CONF_ENABLE_REMOTE_CONTROL = "enable_remote_control"
CONF_ACCEPT_REMOTE_CONTROL_DISCLAIMER = "accept_remote_control_disclaimer"
CONF_UNSANITIZED_DEBUG = "unsanitized_debug"
DEFAULT_REGION = "us-west-2"
DEFAULT_WATCHDOG_INACTIVITY = 5
DEFAULT_UNSANITIZED_DEBUG = False

# Issue #5: rate-limit / backoff envelope. See docs/RATE_LIMITS.md.
DOSING_POLL_INTERVAL_SECONDS = 300                 # 5 min, matches binary_sensor.py timer
ENTITY_REFRESH_INTERVAL_SECONDS = 1800             # 30 min, matches sensor/binary_sensor timers
MQTT_WATCHDOG_MAX_SECONDS = 60                     # cap for the exponential backoff
BACKOFF_EXPONENT_CAP = 5                           # multiplier sequence: 1x, 2x, 4x, 5x, 5x, ...
RATE_LIMITED_BACKOFF_MULTIPLIER = 10               # used for 429 responses without Retry-After

# Issue #3: cloud-outage resilience (stale-tolerant entities).
CONF_CLOUD_STALE_RETENTION_SECONDS = "cloud_stale_retention_seconds"
DEFAULT_CLOUD_STALE_RETENTION_SECONDS = 600        # 10 min: serve cached value with stale: true
MIN_CLOUD_STALE_RETENTION_SECONDS = 30             # below this, no improvement over today
MAX_CLOUD_STALE_RETENTION_SECONDS = 3600           # above 1 hr, refusing to serve cached data is more honest

PLATFORMS: list[str] = ["sensor", "binary_sensor", "button", "select"]

SIGNAL_COLLECTIVE_UPDATED = "hydros_collective_updated_{entry}_{thing}"
SIGNAL_CONFIG_UPDATED = "hydros_config_updated_{entry}_{thing}"

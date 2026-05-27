# Security audit — credential / secret handling

**Audit reference:** Issue [#4](../../issues/4) · **Implemented:** PR (this branch) · **Last reviewed:** commit `1d8fd69` (post-PR #13 merge).

This document records the reproducible credential / secret-handling audit performed against `JLay2026/ha-hydros` and the defensive changes that resulted. Re-run the grep patterns below on any future commit to verify the property still holds.

> Related backlog: [#14](../../issues/14) — third-party `pyhydros` library audit (deferred; defense-in-depth in this fork makes it non-blocking).

---

## Reproducible audit method

Run from repo root:

```bash
# 1. _LOGGER calls referencing sensitive terms
grep -nE '_LOGGER\.(debug|info|warning|error|exception)' custom_components/hydros/*.py \
  | grep -iE '(password|token|secret|cred|mqtt_user|mqtt_pass|auth|api[_-]?key|signature|cookie|session)'

# 2. Logging of entry.data / entry.options / user_input
grep -nE 'entry\.data|entry\.options|user_input' custom_components/hydros/*.py \
  | grep -iE '_LOGGER|log|print'

# 3. HTTP auth-header construction within the integration
grep -nE 'Authorization|Bearer|X-Api-Key|api_key|access_token' custom_components/hydros/*.py

# 4. Full _LOGGER call site listing for visual review
grep -nE '_LOGGER\.(debug|info|warning|error|exception)' custom_components/hydros/*.py

# 5. Credential-handling call sites
grep -nE 'HydrosAPI\(|authenticate|connect_mqtt|password|self\._password|self\._username' \
  custom_components/hydros/*.py
```

## Findings

### ✅ Direct logging — clean

- No `_LOGGER.*` call logs a literal password, token, credential, or config-entry data dict.
- `config_flow.async_step_user` does not log the password on validation failure (the `HydrosAuthError` branch sets `errors["base"] = "invalid_auth"` and never references `user_input` in a log call).
- The integration constructs no HTTP requests itself — all HTTP traffic is delegated to `pyhydros`, so no Authorization headers exist to redact.
- The dosing-logs re-auth path (`hydros_hub.py:318+`) does not include credentials at the call site.

### ⚠️ Indirect risk — mitigated

Four log statements pass exception objects from `pyhydros` to `%s` formatters. The library's exception messages are opaque to this fork — they *could* embed credentials, tokens, or presigned URLs. The fix wraps these with `sanitize_string()` from `custom_components/hydros/sanitizer.py` (the same module added in [#6](../../issues/6) for debug-sample sanitization).

| ID | File:Line | Mitigation |
|---|---|---|
| **AUTH-LOG-1** | `hydros_hub.py` `async_setup` HydrosAuthError/HydrosAPIError branch | `sanitize_string(str(err))` before `%s` |
| **AUTH-LOG-2** | `config_flow.py` `async_step_user` HydrosAPIError branch | `sanitize_string(str(err))` before `%s` |
| **AUTH-LOG-3** | `hydros_hub.py` `async_refresh_dosing_logs` post-re-auth failure | `sanitize_string(str(retry_err))` before `%s` |
| **EXC-LOG-1** | `config_flow.py` `async_step_user` unknown-exception branch | `_LOGGER.exception(...)` replaced with `_LOGGER.error(... type=%s ...)` + `_LOGGER.debug("...", exc_info=True)`. The traceback only emits when the user explicitly enables DEBUG logging for `custom_components.hydros`, so frame-locals captures (Sentry, Datadog, some HA log shippers) don't expose the `password` local at default INFO level. |
| **EXC-LOG-2** | `hydros_hub.py` `async_setup` unknown-exception branch | Same `error` + `debug exc_info` pattern as EXC-LOG-1 (lower risk because `password` is `self._password` not a local, but the code is uniform). |

### ℹ️ Out of scope (per Issue #4 non-goals)

- **HA config-entry encryption at rest.** HA Core stores `.storage/core.config_entries` as plaintext JSON. Encryption is the user's responsibility (full-disk encryption on the HA host). Users running this integration with cloud credentials in the entry should treat the HA host as a credential-bearing system.
- **Replacing username/password with OAuth.** Coralvue does not expose an OAuth endpoint as of `pyhydros==0.4.1`. Out of scope until they do.
- **Auditing `pyhydros` itself.** Tracked separately as [#14](../../issues/14). The fixes above are defense-in-depth; the pyhydros audit raises confidence from "defended against" to "verified safe."

---

## What the audit deliberately does NOT do

- **Does not redact `thing_id` / `thing_name` / `output_name` in logs.** These are device-level identifiers also exposed in HA entity IDs, dashboards, and exported recorder data. Redacting them in logs would hide operational signal without hiding anything that isn't already visible elsewhere.
- **Does not add a custom encryption layer over `entry.data`.** Out of scope; HA Core's responsibility.

---

## Re-audit on every release

The grep patterns above are deterministic. Future contributors changing log call sites in `custom_components/hydros/` should re-run them and update this document if findings change. The `sanitize_string()` wrapper around `%s % err` formatting should be considered the default pattern for any new exception-logging call site in the integration.

If a re-audit produces a finding not covered by the existing `SENSITIVE_KEY_SUBSTRINGS` set or by the value-shape regexes (`EMAIL_RE`, `JWT_RE`, `MQTT_CREDS_RE`, `URL_RE`) in `sanitizer.py`, extend the sanitizer first, then re-run the test suite (`python -m unittest tests.test_sanitizer`) before touching the log call site.

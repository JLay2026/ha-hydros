# Hardening Issues — v0.4.x Fork Line

> **Status (2026-05-26):** All 6 items are now filed as real GitHub Issues (#3-#8) under tracker #2. This file remains as the in-repo index + design rationale; see the linked issues for live status and acceptance criteria.

This fork (`JLay2026/ha-hydros`) hardens [`Bitf1ip/ha-hydros`](https://github.com/Bitf1ip/ha-hydros) v0.3.4 for production use in the [Workshop dashboard project](https://github.com/JLay2026/HA-dashboard). The upstream maintainer accepts contributions (v0.3.3 already credited a JLay2026 patch from the `fix/h1-missing-hub-methods` branch here), so items 1-4 below land here first, then auto-PR upstream via [`.github/workflows/upstream-pr.yml`](.github/workflows/upstream-pr.yml).

**Tracker issue:** [#2](../../issues/2)
**Workflow convention:** see [CONTRIBUTING.md](./CONTRIBUTING.md)
**Tied to:** [HA-dashboard WORKSHOP-DASHBOARD-PLAN.md M2 milestone](https://github.com/JLay2026/HA-dashboard/blob/main/docs/WORKSHOP-DASHBOARD-PLAN.md)
**Decision context:** [HA-dashboard ADR-001](https://github.com/JLay2026/HA-dashboard/blob/main/docs/ADR-001-hobby-dashboards.md)

---

## Items at a glance

| Issue | Item | Phase | Branch prefix | PR upstream? |
|---|---|---|---|---|
| [#3](../../issues/3) | Cloud-outage resilience — graceful degradation + stale-value retention | v0.4.0 | `upstream/` | Yes |
| [#4](../../issues/4) | Credential / secret handling audit | v0.4.0 | `upstream/` | Yes if findings |
| [#5](../../issues/5) | Rate-limit / backoff posture review | v0.4.0 | `upstream/` | Yes |
| [#6](../../issues/6) | MQTT debug-sample sanitization | v0.4.0 | `upstream/` | Yes |
| [#7](../../issues/7) | Document "unavailable ≠ alert" template discipline in README | v0.4.1 | `fork-only/` | No (downstream usage) |
| [#8](../../issues/8) | HA-side guardrail: monitoring-only, no life-safety toggles (README) | v0.4.1 | `fork-only/` | No (downstream usage) |

## Exit criteria for M2

- [ ] v0.4.0 tagged with #3, #4, #5, #6 implemented (code)
- [ ] v0.4.1 tagged with #7, #8 (docs only)
- [ ] Hardened fork installed on HA host; `Bitf1ip/ha-hydros` v0.3.4 uninstalled
- [x] Entity manifest captured into [`HA-dashboard/docs/entity-manifests/hydros.md`](https://github.com/JLay2026/HA-dashboard/blob/main/docs/entity-manifests/hydros.md)
- [ ] ≥1 upstream PR opened back to `Bitf1ip/ha-hydros` (the workflow does this automatically on merge of any `upstream/*` branch — see [CONTRIBUTING.md](./CONTRIBUTING.md))

## Why these specific items

The upstream integration is honest about its scope: monitoring only, controller owns life-safety, cloud-API dependent. These 6 items add operational hardening appropriate to running it in a GitOps-managed HA stack where a dashboard depends on it for visibility — without crossing the line into life-safety automation the upstream author (rightly) refuses to support.

Design rationale and trade-offs live in each linked issue.

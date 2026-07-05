# TODO

This file tracks known follow-up work. Update it with every codebase change, even when the update is only to mark an item done or add a newly discovered task.

## Active

- Make saved Web UI settings apply live without a service restart where practical.
- Add optional authentication before exposing Web UI administration and update actions beyond a trusted LAN.

## Done

- Scaffolded the production project structure.
- Added apcupsd parsing and simulator state.
- Added SNMP v1/v2c GET response path with safe read-only OID registry.
- Added basic SNMP GETNEXT walking support.
- Fixed BER OID handling for large `2.x` object identifier roots.
- Added configuration validation for clearer startup errors.
- Added NUT backend support.
- Added REST API, Prometheus, Home Assistant Discovery, Web UI, and MQTT frontends.
- Added named APC PowerNet enum helpers and tests for QNAP-facing states.
- Added CI and release-build automation.
- Updated README and roadmap wording after completing active TODO items.
- Added Web UI configuration editing for backend, SNMP, API, Prometheus, Home Assistant, MQTT, and logging.
- Updated Raspberry Pi install docs and systemd paths for `/opt/pug`.
- Added full raw backend stat publishing across REST, MQTT, Home Assistant discovery, Prometheus, Web UI, and read-only SNMP.
- Added first-class UPS status publishing across MQTT, Home Assistant, and Prometheus.
- Added human-friendly Web UI labels and formatted status values.
- Added modern Web UI dashboard, separate settings page, and bounded log viewer.
- Added mode-aware UPS diagram paths and restored MQTT/Home Assistant temperature publishing through individual normalized topics.
- Redrew the Web UI UPS diagram to better match line-interactive APC behavior.
- Corrected APC PowerNet battery OID mappings and SNMP types for LibreNMS compatibility.
- Added APC PowerNet frequency, high-precision voltage/load/current, output status, and apparent-load mappings for LibreNMS.
- Expanded Home Assistant MQTT discovery metadata for normalized and known raw APC sensors with correct units, device classes, state classes, and numeric extraction templates.
- Improved the Web UI UPS power-flow diagram with separate desktop/mobile layouts, a left-side bypass path, clearer active/standby styling, and live values on diagram components.
- Moved Web UI raw backend stats to a dedicated Raw Stats page and tightened UPS Details card spacing.
- Replaced fragile Web UI text glyphs with packaged transparent PNG UPS icons and changed the top summary from Self Test to Output Voltage.
- Added project docs, config example, systemd service, and tests.
- Added maintenance rule for `CHANGELOG.md` and `TODO.md`.
- Published repo references, Administration navigation, app footer, and Web UI update workflow.
- Added version bump rule, background update checks, and top-of-page update banner.
- Switched update detection to GitLab Releases with configurable check cadence and persisted latest-release metadata.

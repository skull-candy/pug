# TODO

This file tracks known follow-up work. Update it with every codebase change, even when the update is only to mark an item done or add a newly discovered task.

## Active

- Make saved Web UI settings apply live without a service restart where practical.

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
- Added project docs, config example, systemd service, and tests.
- Added maintenance rule for `CHANGELOG.md` and `TODO.md`.

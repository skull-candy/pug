# TODO

This file tracks known follow-up work. Update it with every codebase change, even when the update is only to mark an item done or add a newly discovered task.

## Active

- Validate APC PowerNet enum values against more QNAP firmware versions.
- Add NUT backend.
- Add MQTT, REST API, Prometheus, Home Assistant Discovery, and Web UI frontends.
- Add packaging and release automation.

## Done

- Scaffolded the production project structure.
- Added apcupsd parsing and simulator state.
- Added SNMP v1/v2c GET response path with safe read-only OID registry.
- Added basic SNMP GETNEXT walking support.
- Fixed BER OID handling for large `2.x` object identifier roots.
- Added configuration validation for clearer startup errors.
- Added project docs, config example, systemd service, and tests.
- Added maintenance rule for `CHANGELOG.md` and `TODO.md`.

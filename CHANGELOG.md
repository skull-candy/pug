# Changelog

All notable changes to PowerPi UPS Gateway are documented here.

This project follows the spirit of Keep a Changelog. Update this file for every codebase change.

## [Unreleased]

### Added

- Initial project scaffold with apcupsd collector, simulator, normalized UPS state, SNMP BER/codec support, OID registry, APC PowerNet mappings, RFC1628 mappings, docs, systemd service, and tests.
- `TODO.md` maintenance file and contribution rule requiring both `CHANGELOG.md` and `TODO.md` to stay current on every codebase update.
- Basic SNMP GETNEXT support using numeric OID ordering, plus tests for walk-style resolution.
- More complete BER object identifier handling for `2.x` roots with large second arcs.
- Configuration validation for backend command, poll interval, SNMP port, community, and supported backend type.
- NUT backend parser and collector support.
- HTTP frontend with REST JSON state, Prometheus metrics, Home Assistant Discovery payloads, health check, and built-in status page.
- Dependency-free MQTT state publisher with retained Home Assistant Discovery messages.
- Named APC PowerNet enum helpers and tests for QNAP-facing status/source values.
- CI and release-build GitHub Actions workflows plus source distribution manifest.
- Roadmap and README cleanup to reflect completed TODO items.
- Web UI configuration form for backend, SNMP, REST API, Prometheus, Home Assistant, MQTT, and logging settings.
- Config save/reload support and safer parsing for quoted values containing `#`.
- Raspberry Pi install docs and systemd service path updated for a repo checkout at `/opt/pug`.

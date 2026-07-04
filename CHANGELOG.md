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
- Full raw backend stat publishing across REST, MQTT, Home Assistant discovery, Prometheus, Web UI, and a read-only SNMP raw-status subtree.
- First-class UPS status publishing through MQTT status topics, Home Assistant status/binary sensors, and Prometheus status info.
- Human-friendly Web UI status and raw-stat labels with units and readable boolean values.
- Modern Web UI dashboard with navigation, overview cards, animated power-flow diagram, separate settings page, and bounded log viewer.
- Mode-aware UPS diagram paths for line/AVR, battery, bypass, and conversion states.
- Individual MQTT topics for normalized values, including restored Home Assistant temperature publishing via `internal_temperature_c`.
- Redrawn Web UI power-flow diagram around line-interactive UPS topology with clearer AVR, bypass, battery, inverter, and load blocks.
- Corrected APC PowerNet battery OID mappings and SNMP types for LibreNMS compatibility.
- Added APC PowerNet input/output frequency, high-precision voltage/load/current, output status, and apparent-load mappings for LibreNMS.
- Expanded Home Assistant MQTT discovery metadata so normalized and known raw APC sensors publish correct units, device classes, state classes, and numeric extraction templates.
- Improved the Web UI UPS power-flow diagram with separate desktop/mobile layouts, a left-side bypass path, clearer active/standby styling, and live values on diagram components.
- Moved Web UI raw backend stats to a dedicated Raw Stats page and tightened UPS Details card spacing.
- Replaced fragile Web UI text glyphs with packaged transparent PNG UPS icons and changed the top summary from Self Test to Output Voltage.
- Grouped Web UI administration pages under an Administration menu while keeping Dashboard top-level.
- Added an app-wide footer with version, copyright, and "Developed By: Ahsan Muhammad".
- Added a Web UI Updates page that checks the public repository, installs fast-forward updates, reinstalls PUG, and restarts the service.
- Updated documentation for the public repository at `https://git.vns.ae/ahsan/pug`.
- Added background update checks with a top-of-page banner when a newer version is available.
- Tightened dashboard UPS Details row spacing and bumped the application version to `0.1.1`.

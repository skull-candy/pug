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

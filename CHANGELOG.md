# Changelog

All notable changes to PowerPi UPS Gateway are documented here.

This project follows the spirit of Keep a Changelog. Update this file for every codebase change.

## [Unreleased]

### Added

- Added a read-only Proxmox test and verification action covering API credentials, TLS, node status, version, quorum, HA, storage, and Ceph health; bumped the feature version to `0.2.11`.
- Replaced the pipe-delimited Proxmox hosts textarea with repeatable structured host fields for name, address, node, token ID, secret file, and shutdown order; bumped the feature version to `0.2.10`.
- Fixed Discord webhook delivery through Discord/Cloudflare by sending an explicit PUG user agent and JSON accept header; bumped the feature version to `0.2.9`.
- Refreshed GitLab release metadata during feature-branch checks, preserved cached release details when GitLab is temporarily unavailable, clarified the Latest Release label, and bumped the feature version to `0.2.8`.
- Added direct Discord webhook entry, separate Discord/email test buttons, and example tooltips for Proxmox, HA, and notification settings; protected saved configuration with owner-only permissions and bumped the feature version to `0.2.7`.
- Backported persistent update diagnostics and installed-package repository discovery to the Proxmox feature branch and aligned its displayed version with `0.2.6`.
- Guarded Proxmox shutdown automation with persisted outage state, UPS thresholds, dry-run support, per-node API tokens, HA freeze and manual/automatic-safe rearming, quorum/storage/Ceph checks, Discord and SMTP alerts, Web UI controls, and audit history.
- Bumped the application version to `0.2.0` for the power-actions feature set.
- Added release and feature-branch update channels, remote branch discovery and compatibility warnings, exact release-tag installation, commit-based branch checks, visible check failures, clean-worktree protection, and bumped the version to `0.2.1`.
- Moved Proxmox, HA recovery, Discord, and email configuration to a dedicated Proxmox Settings page, made feature-branch selection automatically choose the Branch channel, and bumped the PVE feature version to `0.2.3`.
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
- Saving Web UI settings now restarts the `powerpi-ups-gateway` service after writing `config.yaml`.
- Switched update detection to GitLab Releases, with configurable self-hosted GitLab base URL, release check interval, persisted latest release metadata, and non-blocking release banners.
- Bumped the application version to `0.1.2`.
- Refined the dashboard power-flow diagram for battery charging/on-battery states, removed overview icons, tightened UPS Details spacing, improved live refresh, and added configurable timestamp timezone display.
- Bumped the application version to `0.1.3`.
- Restored UPS Details text sizing while keeping compact row padding and made the manual update check button force a GitLab Releases check.
- Bumped the application version to `0.1.4`.
- Bumped the application version to `0.1.5` for the Git tag and release refresh.
- Added diagnostic abort support, kept battery calibration stdin open for apctest progress/abort tracking, restored apcupsd after abort, and added Settings controls for starting, stopping, and restarting apcupsd.
- Bumped the application version to `0.1.6`.
- Added optional HTTP Basic authentication for the Web UI/API with disabled, always-on, and remote-only modes plus trusted IP/CIDR bypass networks.
- Bumped the application version to `0.1.7`.

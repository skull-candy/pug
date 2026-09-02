## 🚀 PowerPi UPS Gateway

Turn your Raspberry Pi into a universal UPS monitoring gateway.

<p align="center">
<img src="https://vns.ae/assets/images/blog/powerpi-ups-gateway-dashboard.png"
     alt="PowerPi UPS Gateway Web Dashboard"
     width="900">
</p>



# PowerPi UPS Gateway

PowerPi UPS Gateway (PUG) is a public UPS protocol gateway for Raspberry Pi and Linux. It reads UPS status from one backend, normalizes it into a shared state object, and exposes that state through SNMP.

Public repository: `https://git.vns.ae/ahsan/pug`

The first target client is QNAP. PUG identifies itself as an APC Smart-UPS over SNMP and serves the APC PowerNet OIDs QNAP expects.

## Why This Exists

Some UPS setups are easy for Linux to read but awkward for NAS appliances to consume. PUG bridges that gap: one collector talks to the UPS backend, while protocol frontends read from the same cached state.

Current backend:

- `apcupsd` via `apcaccess status localhost:3551`
- NUT via commands such as `upsc ups@localhost`
- Built-in simulator for local testing

Current frontend:

- SNMP v1/v2c GET and basic GETNEXT over UDP
- REST JSON, Prometheus metrics, Home Assistant Discovery, Web UI, and MQTT state publishing

## Architecture

```text
+----------------+       +----------------+       +----------------+
| apcupsd / sim  | ----> | collector loop | ----> | shared UPSState |
+----------------+       +----------------+       +----------------+
                                                         |
                                                         v
                                                  +-------------+
                                                  | SNMP server |
                                                  +-------------+
                                                         |
                                                         v
                                                  QNAP / clients
```

Only the collector reads the UPS backend. SNMP, MQTT, REST, Prometheus, Home Assistant, and Web UI frontends read from `UPSState`.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
if (!(Test-Path config/config.yaml)) { Copy-Item config/config.example.yaml config/config.yaml }
python -m pug.main --simulator --config config/config.yaml
```

On Linux/Raspberry Pi:

```sh
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip apcupsd
cd /opt
sudo git clone https://git.vns.ae/ahsan/pug.git pug
sudo chown -R "$USER:$USER" /opt/pug
cd /opt/pug
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp -n config/config.example.yaml config/config.yaml
sudo python -m pug.main --simulator --config config/config.yaml
```

`config/config.yaml` is ignored by Git so local settings are not overwritten by pulls. Keep defaults in `config/config.example.yaml`; copy it again only when you intentionally want to reset your local config.

The systemd service file assumes the repo lives at `/opt/pug`. If your checkout is nested somewhere else, such as `/opt/powerpi-ups-gateway/pug`, either move it to `/opt/pug` or edit `WorkingDirectory` and `ExecStart` in `systemd/powerpi-ups-gateway.service` before installing the service.

UDP/161 is privileged on Linux. Run as root or grant `CAP_NET_BIND_SERVICE` to the Python interpreter or service wrapper.

For unprivileged local testing, set the SNMP port in `config/config.yaml` to a high port such as `1161`.

HTTP defaults to port `8080`:

- `http://<host>:8080/api/state`
- `http://<host>:8080/api/raw`
- `http://<host>:8080/metrics`
- `http://<host>:8080/homeassistant`
- `http://<host>:8080/ui` dashboard with power-flow diagram and UPS details
- `http://<host>:8080/diagnostics` self-test and battery calibration controls
- `http://<host>:8080/settings` configuration
- `http://<host>:8080/logs` bounded PUG log and apcupsd event log tail view
- `http://<host>:8080/updates` check, download, and install updates from the public repository
- `http://<host>:8080/power-actions` Proxmox shutdown, HA recovery, and notification status
- `http://<host>:8080/proxmox-settings` Proxmox nodes, shutdown policy, HA recovery, Discord, and email configuration

## Proxmox Power Actions

PUG can perform a guarded, graceful Proxmox cluster shutdown when sustained UPS-on-battery criteria are met. The feature is disabled, disarmed, and in dry-run mode by default. It supports direct API-token connections to every node, quorum/storage/Ceph preflight checks, cluster-wide HA disarm in `freeze` mode, manual or health-gated automatic HA rearming after stable power returns, and Discord webhook or SMTP alerts.

Configure each server using the structured host rows on Proxmox Settings: name, host/IP, Proxmox node, API token ID, token secret file, and shutdown order; higher order values shut down first. The stored configuration remains compatible with the original `name|host|node|token_id|token_secret_file|order` format. Save and use **Test and Verify Proxmox Hosts** to perform read-only API credential, TLS, node, quorum, HA, storage, and Ceph checks. Discord webhook URLs can be entered directly on the Proxmox Settings page or read from a root-readable secret file; SMTP passwords and Proxmox tokens remain file-based. Direct webhook values are masked in the UI/API and `config.yaml` is written with owner-only permissions. Use the per-provider test buttons after saving. Keep the Raspberry Pi and management network on UPS power, validate TLS with the Proxmox cluster CA, and complete a dry-run plus controlled outage test before enabling live actions.

PUG only rearms HA automatically when its persisted outage record shows that PUG performed the disarm. Manual recovery is the default. While HA is disarmed in `freeze` mode, automatic HA recovery is unavailable and HA-managed guests remain frozen until HA is rearmed.

## Update Channels and Feature Sets

The Updates page supports two channels. **Stable releases** compare semantic versions from GitLab Releases and install the exact selected release tag. **Feature branch** discovers remote branches, compares the local and remote commit IDs, and can switch the checkout to a configured feature set such as `feature/proxmox-power-actions`. The repository must have a clean worktree before either installation path runs.

Branch profiles are configured as `label|branch|description`. The UI checks whether a selected branch contains the branch-switching updater and warns when switching to an older or incompatible branch could require Git CLI access to return. Update-check failures remain visible on the page instead of being treated as a successful idle check.


## ⚡ Live Power Flow Monitoring

<p align="center">
<img src="https://vns.ae/assets/images/blog/powerpi-ups-gateway-live-power-flow.png"
     alt="UPS Live Power Flow Diagram"
     width="900">
</p>


The Web UI is the always-on control plane. The header keeps Dashboard top-level and groups Raw Stats, Diagnostics, Settings, Logs, Updates, and Metrics under Administration. The dashboard shows a live mode-aware UPS power-flow diagram, overview cards, UPS details, and raw backend stats without page reloads. The diagram highlights line/AVR, battery, bypass, or conversion path based on UPS status and input/output voltage. Diagnostics live on `/diagnostics`; use that page to start or abort an apcupsd self-test or battery calibration and watch the live command status, latest UPS status, and command output. Settings live on `/settings`; use that page to edit backend, SNMP, API, Prometheus, Home Assistant, MQTT, logging, display timezone, diagnostics, GitLab Releases update settings, and apcupsd service state. Save writes `config.yaml` and restarts the `powerpi-ups-gateway` service to apply backend, listener, SNMP, and MQTT runtime changes. Updates live on `/updates`; use that page to check the latest GitLab Release, view latest release metadata, install from the local checkout, reinstall PUG, and restart the systemd service. Logs live on `/logs` and tail both the PUG log and apcupsd events file, defaulting to `/var/log/apcupsd.events`. Both views update without page reloads and only read the configured number of lines, so huge log files do not slow the UI.

HTTP Basic authentication can be enabled from Settings or under the `http` config section. Set `auth_mode` to `always` to require auth for every client, or `remote` to require auth only outside `auth_bypass_networks`. The default no-auth networks cover localhost and common private LAN IPv4/IPv6 ranges; replace that list with specific IPs or CIDR networks when you want a narrower trusted set.

Diagnostics stop `apcupsd`, run `apctest`, then start `apcupsd` again by default. They use `apctest` menu selection `2` for self-test and `10` for battery calibration. The abort button sends Enter to apctest, terminates it if it does not exit, and restores `apcupsd`. Monitoring is unavailable while `apcupsd` is stopped, and battery calibration can run for a long time while intentionally discharging the UPS battery. Adjust the configured diagnostics commands if your host needs a wrapper script for service control or sudo.

All raw backend stats from `apcaccess` or NUT are preserved in `UPSState.raw` and published through the enabled frontends:

- REST: `/api/state` includes `raw` and `raw_stats`; `/api/raw` returns only raw backend values.
- MQTT: full state goes to `powerpi/ups`, UPS status goes to `powerpi/ups/status`, status flags go to `powerpi/ups/online`, `powerpi/ups/on_battery`, and `powerpi/ups/replace_battery`, raw JSON goes to `powerpi/ups/raw`, and every raw key gets `powerpi/ups/raw/<key>`.
- MQTT normalized values are also published individually, such as `powerpi/ups/internal_temperature_c`, `powerpi/ups/input_voltage`, and `powerpi/ups/load_percent`.
- Home Assistant: discovery includes the main normalized sensors, a UPS status sensor first, online/on-battery/replace-battery binary sensors, and raw-key sensors marked as diagnostic entities.
- Prometheus: normalized gauges, `powerpi_ups_status_info`, plus `powerpi_ups_raw_numeric` and `powerpi_ups_raw_info`.
- Web UI: status table plus a raw backend stats table.
- SNMP: known `apcaccess` raw keys are exposed as read-only strings under `1.3.6.1.4.1.318.1.1.1.99.1`.

If the UPS is removed from Home Assistant's MQTT integration and does not reappear, open `/settings` and use **Republish Discovery**. PUG clears the retained Home Assistant discovery topics and immediately publishes fresh retained configs.

Install as a service:

```sh
sudo cp systemd/powerpi-ups-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now powerpi-ups-gateway
sudo journalctl -u powerpi-ups-gateway -f
```

## QNAP Setup

1. Start PUG on the Raspberry Pi.
2. In QNAP UPS settings, choose SNMP.
3. Enter the PowerPi host IP.
4. Use community `public` unless changed in config.

QNAP first probes `sysObjectID` at `1.3.6.1.2.1.1.2.0`. PUG returns APC PowerNet enterprise identity `1.3.6.1.4.1.318.1.1.1`, then answers the APC PowerNet status OIDs QNAP asks for.

## Security

SNMP v1/v2c community strings are not secure authentication. Use this on trusted networks only, bind to a specific interface where possible, and change the default community for real deployments.

## Maintenance Files

Every codebase update should keep these files current:

- `CHANGELOG.md` for user-visible changes.
- `TODO.md` for known follow-up work and task status.

## Roadmap

See `ROADMAP.md` and `TODO.md`.

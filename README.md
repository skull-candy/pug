# PowerPi UPS Gateway

PowerPi UPS Gateway (PUG) is a universal UPS protocol gateway for Raspberry Pi and Linux. It reads UPS status from one backend, normalizes it into a shared state object, and exposes that state through SNMP.

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
python -m pug.main --simulator --config config/config.yaml
```

On Linux/Raspberry Pi:

```sh
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip apcupsd
cd /opt
sudo git clone <your-repo-url> pug
sudo chown -R "$USER:$USER" /opt/pug
cd /opt/pug
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
sudo python -m pug.main --simulator --config config/config.yaml
```

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

The Web UI is the always-on control plane. The dashboard shows a mode-aware UPS power-flow diagram, overview cards, UPS details, and raw backend stats. The diagram highlights line/AVR, battery, bypass, or conversion path based on UPS status and input/output voltage. Diagnostics live on `/diagnostics`; use that page to start an apcupsd self-test or battery calibration and watch the live command status, latest UPS status, and command output. Settings live on `/settings`; use that page to edit backend, SNMP, API, Prometheus, Home Assistant, MQTT, logging, and diagnostics settings. Save writes `config.yaml`; restart the service to apply backend, listener, SNMP, and MQTT runtime changes. Logs live on `/logs` and tail both the PUG log and apcupsd events file, defaulting to `/var/log/apcupsd.events`. Both views only read the configured number of lines, so huge log files do not slow the UI.

Diagnostics default to `apctest` menu selection `2` for self-test and `10` for battery calibration. Some apcupsd installations require stopping the `apcupsd` daemon before running `apctest`, and battery calibration can run for a long time while intentionally discharging the UPS battery. Adjust the configured diagnostics commands if your host needs a wrapper script for service control or sudo.

All raw backend stats from `apcaccess` or NUT are preserved in `UPSState.raw` and published through the enabled frontends:

- REST: `/api/state` includes `raw` and `raw_stats`; `/api/raw` returns only raw backend values.
- MQTT: full state goes to `powerpi/ups`, UPS status goes to `powerpi/ups/status`, status flags go to `powerpi/ups/online`, `powerpi/ups/on_battery`, and `powerpi/ups/replace_battery`, raw JSON goes to `powerpi/ups/raw`, and every raw key gets `powerpi/ups/raw/<key>`.
- MQTT normalized values are also published individually, such as `powerpi/ups/internal_temperature_c`, `powerpi/ups/input_voltage`, and `powerpi/ups/load_percent`.
- Home Assistant: discovery includes the main normalized sensors, a UPS status sensor, online/on-battery/replace-battery binary sensors, and raw-key sensors.
- Prometheus: normalized gauges, `powerpi_ups_status_info`, plus `powerpi_ups_raw_numeric` and `powerpi_ups_raw_info`.
- Web UI: status table plus a raw backend stats table.
- SNMP: known `apcaccess` raw keys are exposed as read-only strings under `1.3.6.1.4.1.318.1.1.1.99.1`.

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

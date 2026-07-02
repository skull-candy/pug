# PowerPi UPS Gateway

PowerPi UPS Gateway (PUG) is a universal UPS protocol gateway for Raspberry Pi and Linux. It reads UPS status from one backend, normalizes it into a shared state object, and exposes that state through SNMP.

The first target client is QNAP. PUG identifies itself as an APC Smart-UPS over SNMP and serves the APC PowerNet OIDs QNAP expects.

## Why This Exists

Some UPS setups are easy for Linux to read but awkward for NAS appliances to consume. PUG bridges that gap: one collector talks to the UPS backend, while protocol frontends read from the same cached state.

Current backend:

- `apcupsd` via `apcaccess status localhost:3551`
- Built-in simulator for local testing

Current frontend:

- SNMP v1/v2c GET and basic GETNEXT over UDP

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

Only the collector reads the UPS backend. SNMP and future MQTT, REST, Prometheus, or Home Assistant frontends read from `UPSState`.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m pug.main --simulator --config config/config.yaml
```

On Linux/Raspberry Pi:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
sudo python -m pug.main --simulator --config config/config.yaml
```

UDP/161 is privileged on Linux. Run as root or grant `CAP_NET_BIND_SERVICE` to the Python interpreter or service wrapper.

For unprivileged local testing, set the SNMP port in `config/config.yaml` to a high port such as `1161`.

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

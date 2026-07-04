# Frontends

All frontends read from the shared `UPSState`.

## HTTP

When enabled, the HTTP frontend serves:

- `/api/state`: normalized UPS state as JSON.
- `/api/raw`: raw backend key/value output.
- `/metrics`: Prometheus text exposition.
- `/homeassistant`: Home Assistant MQTT discovery config payloads as JSON.
- `/ui` and `/`: small status page.
- `/diagnostics`: self-test and battery calibration controls with live command status.
- `/settings`: configuration form.
- `/logs`: bounded PUG log and apcupsd event log tail view.
- `/healthz`: health check.

The Web UI at `/ui` is a dashboard with metric cards, a mode-aware animated power-flow diagram, UPS details, and raw backend stats. The diagram highlights line/AVR mode when the UPS is online and input/output voltage are close, battery mode when on battery, bypass mode when status reports bypass, and conversion mode when online with a meaningful input/output voltage difference.

The diagnostics page at `/diagnostics` can start one apcupsd diagnostic command at a time without reloading the page. By default it stops `apcupsd`, runs `apctest` with menu selection `2` for self-test or `10` for battery calibration, then starts `apcupsd` again. It shows running/completed/failed status, the latest UPS status values, and captured command output. Monitoring is unavailable while `apcupsd` is stopped. Battery calibration may discharge the UPS for an extended period; configure wrapper commands if the target host needs different service control or sudo.

The settings page at `/settings` includes a configuration form for:

- Backend type, command, and poll interval.
- SNMP enablement, listen address, port, community, and developer logging.
- REST API, Prometheus, and Home Assistant endpoint toggles.
- MQTT enablement, broker, topics, credentials, and publish interval.
- Logging level.
- Log file path and log tail line count.
- Diagnostics preparation/restore commands, apctest menu selections, and command timeout.

Saving the form writes `config.yaml`. Restart the service to apply backend, listener, SNMP, and MQTT runtime changes.

The logs page reads only the last configured number of lines from the configured PUG log file and apcupsd events file. It does not load full files into memory. The default apcupsd events path is `/var/log/apcupsd.events`, and it can be changed from Settings.

## MQTT

The MQTT publisher sends the normalized UPS state as JSON to `mqtt.topic_prefix`. That payload includes both `raw` and `raw_stats`.

It also publishes:

- `<topic_prefix>/status`: UPS status text such as `ONLINE REPLACEBATT`.
- `<topic_prefix>/online`, `<topic_prefix>/on_battery`, `<topic_prefix>/replace_battery`: `ON` or `OFF` status flags.
- `<topic_prefix>/<normalized_key>`: one topic per normalized value, including `internal_temperature_c`.
- `<topic_prefix>/raw`: all raw backend values as JSON.
- `<topic_prefix>/raw/<key>`: one topic per raw backend key.
- Retained Home Assistant discovery config messages under `mqtt.discovery_prefix`.

Home Assistant discovery publishes the UPS status sensor first, then classifies normalized UPS values with appropriate sensor metadata, including voltage, current, frequency, temperature, battery percentage, duration, power, apparent power, and diagnostic threshold sensors. Known `apcaccess` raw keys such as `LINEV`, `OUTCURNT`, `LINEFREQ`, `ITEMP`, `LOADPCT`, `LOADAPNT`, `NOMPOWER`, and `NOMAPNT` are also typed when discovery is published. All raw-key entities are marked as diagnostic entities. Raw values that include units are parsed with a value template so Home Assistant stores the numeric part as the sensor state.

If a user removes the UPS from Home Assistant's MQTT integration, the Settings page can republish discovery. This clears retained discovery config topics and publishes fresh retained configs plus current state, which prompts Home Assistant to rediscover the UPS.

MQTT support is implemented with a tiny MQTT 3.1.1 publisher and no runtime dependency.

## SNMP

The SNMP frontend exposes QNAP-compatible APC PowerNet OIDs and a small RFC1628 subset. It supports GET and basic GETNEXT.

Known `apcaccess` raw keys are also exposed as read-only text values under `1.3.6.1.4.1.318.1.1.1.99.1`. Each key gets two OIDs: `<row>.1.0` for the key name and `<row>.2.0` for the value.

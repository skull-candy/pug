# Frontends

All frontends read from the shared `UPSState`.

## HTTP

When enabled, the HTTP frontend serves:

- `/api/state`: normalized UPS state as JSON.
- `/api/raw`: raw backend key/value output.
- `/metrics`: Prometheus text exposition.
- `/homeassistant`: Home Assistant MQTT discovery config payloads as JSON.
- `/ui` and `/`: small status page.
- `/settings`: configuration form.
- `/logs`: bounded log tail view.
- `/healthz`: health check.

The Web UI at `/ui` is a dashboard with metric cards, an animated power-flow diagram, UPS details, and raw backend stats.

The settings page at `/settings` includes a configuration form for:

- Backend type, command, and poll interval.
- SNMP enablement, listen address, port, community, and developer logging.
- REST API, Prometheus, and Home Assistant endpoint toggles.
- MQTT enablement, broker, topics, credentials, and publish interval.
- Logging level.
- Log file path and log tail line count.

Saving the form writes `config.yaml`. Restart the service to apply backend, listener, SNMP, and MQTT runtime changes.

The logs page reads only the last configured number of lines from the configured log file. It does not load the full file into memory.

## MQTT

The MQTT publisher sends the normalized UPS state as JSON to `mqtt.topic_prefix`. That payload includes both `raw` and `raw_stats`.

It also publishes:

- `<topic_prefix>/status`: UPS status text such as `ONLINE REPLACEBATT`.
- `<topic_prefix>/online`, `<topic_prefix>/on_battery`, `<topic_prefix>/replace_battery`: `ON` or `OFF` status flags.
- `<topic_prefix>/raw`: all raw backend values as JSON.
- `<topic_prefix>/raw/<key>`: one topic per raw backend key.
- Retained Home Assistant discovery config messages under `mqtt.discovery_prefix`.

MQTT support is implemented with a tiny MQTT 3.1.1 publisher and no runtime dependency.

## SNMP

The SNMP frontend exposes QNAP-compatible APC PowerNet OIDs and a small RFC1628 subset. It supports GET and basic GETNEXT.

Known `apcaccess` raw keys are also exposed as read-only text values under `1.3.6.1.4.1.318.1.1.1.99.1`. Each key gets two OIDs: `<row>.1.0` for the key name and `<row>.2.0` for the value.

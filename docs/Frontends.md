# Frontends

All frontends read from the shared `UPSState`.

## HTTP

When enabled, the HTTP frontend serves:

- `/api/state`: normalized UPS state as JSON.
- `/metrics`: Prometheus text exposition.
- `/homeassistant`: Home Assistant MQTT discovery config payloads as JSON.
- `/ui` and `/`: small status page.
- `/healthz`: health check.

The Web UI at `/ui` includes a configuration form for:

- Backend type, command, and poll interval.
- SNMP enablement, listen address, port, community, and developer logging.
- REST API, Prometheus, and Home Assistant endpoint toggles.
- MQTT enablement, broker, topics, credentials, and publish interval.
- Logging level.

Saving the form writes `config.yaml`. Restart the service to apply backend, listener, SNMP, and MQTT runtime changes.

## MQTT

The MQTT publisher sends the normalized UPS state as JSON to `mqtt.topic_prefix`. It also publishes retained Home Assistant discovery config messages under `mqtt.discovery_prefix`.

MQTT support is implemented with a tiny MQTT 3.1.1 publisher and no runtime dependency.

## SNMP

The SNMP frontend exposes QNAP-compatible APC PowerNet OIDs and a small RFC1628 subset. It supports GET and basic GETNEXT.

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event
from typing import Any
from urllib.parse import parse_qs

from pug.config import (
    AppConfig,
    BackendConfig,
    ConfigError,
    HttpConfig,
    LoggingConfig,
    MqttConfig,
    SnmpConfig,
    format_command,
    load_config,
    parse_command,
    save_config,
    validate_config,
)
from pug.frontends.homeassistant import discovery_payloads
from pug.frontends.prometheus import render_metrics
from pug.state import StateStore

LOGGER = logging.getLogger(__name__)


class HttpFrontend:
    def __init__(
        self,
        store: StateStore,
        config_path: str | Path,
        config: AppConfig,
        listen: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        self.store = store
        self.config_path = Path(config_path)
        self.config = config
        self.listen = listen
        self.port = port

    def serve_forever(self, stop: Event) -> None:
        handler = self._handler()
        server = ThreadingHTTPServer((self.listen, self.port), handler)
        server.timeout = 1
        LOGGER.info("HTTP frontend listening on %s:%s", self.listen, self.port)
        try:
            while not stop.is_set():
                server.handle_request()
        finally:
            server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        store = self.store
        frontend = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                state = store.get()
                config = frontend.current_config()
                if self.path in {"/", "/ui"}:
                    self._send(
                        200,
                        "text/html; charset=utf-8",
                        render_control_page(state.to_dict(), config).encode(),
                    )
                elif self.path == "/api/state":
                    if config.http.api_enabled:
                        self._send_json(state.to_dict())
                    else:
                        self._send_json({"error": "api disabled"}, status=404)
                elif self.path == "/api/config":
                    if config.http.api_enabled:
                        self._send_json(config_to_public_dict(config))
                    else:
                        self._send_json({"error": "api disabled"}, status=404)
                elif self.path == "/metrics":
                    if config.http.prometheus_enabled:
                        self._send(200, "text/plain; version=0.0.4; charset=utf-8", render_metrics(state).encode())
                    else:
                        self._send_json({"error": "prometheus disabled"}, status=404)
                elif self.path == "/homeassistant":
                    if config.http.homeassistant_enabled:
                        self._send_json(
                            discovery_payloads(
                                state,
                                config.mqtt.topic_prefix,
                                config.mqtt.discovery_prefix,
                            )
                        )
                    else:
                        self._send_json({"error": "homeassistant disabled"}, status=404)
                elif self.path == "/healthz":
                    self._send_json({"ok": True, "source_backend": state.source_backend})
                else:
                    self._send_json({"error": "not found"}, status=404)

            def do_POST(self) -> None:
                if self.path != "/config":
                    self._send_json({"error": "not found"}, status=404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                form = parse_qs(body, keep_blank_values=True)
                try:
                    config = config_from_form(form)
                    save_config(config, frontend.config_path)
                    frontend.config = config
                except (ConfigError, ValueError) as exc:
                    self._send(
                        400,
                        "text/html; charset=utf-8",
                        render_message_page("Configuration Error", str(exc), frontend.current_config()).encode(),
                    )
                    return
                self._send(
                    200,
                    "text/html; charset=utf-8",
                    render_message_page(
                        "Configuration Saved",
                        "Settings were saved. Restart the service to apply listener, backend, SNMP, and MQTT runtime changes.",
                        config,
                    ).encode(),
                )

            def log_message(self, format: str, *args: Any) -> None:
                LOGGER.debug("HTTP %s - %s", self.client_address[0], format % args)

            def _send_json(self, payload: Any, status: int = 200) -> None:
                self._send(status, "application/json", json.dumps(payload, sort_keys=True).encode())

            def _send(self, status: int, content_type: str, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def current_config(self) -> AppConfig:
        try:
            self.config = load_config(self.config_path)
        except (ConfigError, OSError):
            LOGGER.exception("failed to reload config for Web UI")
        return self.config


def config_from_form(form: dict[str, list[str]]) -> AppConfig:
    config = AppConfig(
        backend=BackendConfig(
            type=_field(form, "backend_type"),
            command=parse_command(_field(form, "backend_command")),
            poll_interval_seconds=float(_field(form, "backend_poll_interval_seconds")),
        ),
        snmp=SnmpConfig(
            enabled=_checked(form, "snmp_enabled"),
            listen=_field(form, "snmp_listen"),
            port=int(_field(form, "snmp_port")),
            community=_field(form, "snmp_community"),
            developer_log=_checked(form, "snmp_developer_log"),
        ),
        http=HttpConfig(
            enabled=True,
            listen=_field(form, "http_listen"),
            port=int(_field(form, "http_port")),
            api_enabled=_checked(form, "http_api_enabled"),
            prometheus_enabled=_checked(form, "http_prometheus_enabled"),
            homeassistant_enabled=_checked(form, "http_homeassistant_enabled"),
        ),
        mqtt=MqttConfig(
            enabled=_checked(form, "mqtt_enabled"),
            host=_field(form, "mqtt_host"),
            port=int(_field(form, "mqtt_port")),
            client_id=_field(form, "mqtt_client_id"),
            topic_prefix=_field(form, "mqtt_topic_prefix"),
            discovery_prefix=_field(form, "mqtt_discovery_prefix"),
            username=_field(form, "mqtt_username"),
            password=_field(form, "mqtt_password"),
            publish_interval_seconds=float(_field(form, "mqtt_publish_interval_seconds")),
        ),
        logging=LoggingConfig(level=_field(form, "logging_level")),
    )
    validate_config(config)
    return config


def config_to_public_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "backend": {
            "type": config.backend.type,
            "command": config.backend.command,
            "poll_interval_seconds": config.backend.poll_interval_seconds,
        },
        "snmp": {
            "enabled": config.snmp.enabled,
            "listen": config.snmp.listen,
            "port": config.snmp.port,
            "community": config.snmp.community,
            "developer_log": config.snmp.developer_log,
        },
        "http": {
            "enabled": config.http.enabled,
            "listen": config.http.listen,
            "port": config.http.port,
            "api_enabled": config.http.api_enabled,
            "prometheus_enabled": config.http.prometheus_enabled,
            "homeassistant_enabled": config.http.homeassistant_enabled,
        },
        "mqtt": {
            "enabled": config.mqtt.enabled,
            "host": config.mqtt.host,
            "port": config.mqtt.port,
            "client_id": config.mqtt.client_id,
            "topic_prefix": config.mqtt.topic_prefix,
            "discovery_prefix": config.mqtt.discovery_prefix,
            "username": config.mqtt.username,
            "password": "********" if config.mqtt.password else "",
            "publish_interval_seconds": config.mqtt.publish_interval_seconds,
        },
        "logging": {"level": config.logging.level},
    }


def render_control_page(state: dict[str, Any], config: AppConfig) -> str:
    title = _escape(str(state["name"]))
    rows = "\n".join(
        f"<tr><th>{_escape(key)}</th><td>{_escape(str(value))}</td></tr>"
        for key, value in state.items()
        if key != "raw"
    )
    form = render_config_form(config)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} - PowerPi UPS Gateway</title>
  <style>
    body {{ font: 16px system-ui, sans-serif; margin: 0; color: #17202a; background: #f6f8fa; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    section {{ background: #fff; border: 1px solid #d8dee4; border-radius: 8px; padding: 18px; margin: 0 0 18px; }}
    h1, h2 {{ margin-top: 0; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #d8dee4; padding: .5rem; text-align: left; }}
    th {{ width: 18rem; color: #57606a; font-weight: 600; }}
    form {{ display: grid; gap: 16px; }}
    fieldset {{ border: 1px solid #d8dee4; border-radius: 8px; padding: 14px; }}
    legend {{ font-weight: 700; padding: 0 6px; }}
    label {{ display: grid; gap: 4px; margin: 10px 0; }}
    input, select {{ font: inherit; padding: 8px; border: 1px solid #afb8c1; border-radius: 6px; }}
    input[type="checkbox"] {{ width: 18px; height: 18px; }}
    .check {{ display: flex; align-items: center; gap: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px 18px; }}
    button {{ font: inherit; padding: 10px 14px; border: 0; border-radius: 6px; background: #0969da; color: white; cursor: pointer; }}
    .hint {{ color: #57606a; font-size: 14px; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <section>
      <h2>Status</h2>
      <table>{rows}</table>
    </section>
    <section>
      <h2>Configuration</h2>
      <p class="hint">Save writes config.yaml. Restart the service to apply backend, listener, SNMP, and MQTT runtime changes.</p>
      {form}
    </section>
  </main>
</body>
</html>
"""


def render_config_form(config: AppConfig) -> str:
    return f"""<form method="post" action="/config">
  <fieldset>
    <legend>Backend</legend>
    <div class="grid">
      <label>Type
        <select name="backend_type">
          <option value="apcupsd"{_selected(config.backend.type, "apcupsd")}>apcupsd</option>
          <option value="nut"{_selected(config.backend.type, "nut")}>NUT</option>
        </select>
      </label>
      <label>Poll interval seconds
        <input name="backend_poll_interval_seconds" type="number" min="1" step="0.1" value="{_escape(str(config.backend.poll_interval_seconds))}">
      </label>
    </div>
    <label>Command
      <input name="backend_command" value="{_escape(format_command(config.backend.command))}">
    </label>
  </fieldset>

  <fieldset>
    <legend>SNMP</legend>
    <label class="check"><input name="snmp_enabled" type="checkbox"{_checked_attr(config.snmp.enabled)}> Enable SNMP</label>
    <label class="check"><input name="snmp_developer_log" type="checkbox"{_checked_attr(config.snmp.developer_log)}> Developer hit/miss logging</label>
    <div class="grid">
      <label>Listen address <input name="snmp_listen" value="{_escape(config.snmp.listen)}"></label>
      <label>Port <input name="snmp_port" type="number" min="1" max="65535" value="{config.snmp.port}"></label>
      <label>Community <input name="snmp_community" value="{_escape(config.snmp.community)}"></label>
    </div>
  </fieldset>

  <fieldset>
    <legend>Web, API, Prometheus, Home Assistant</legend>
    <p class="hint">The Web UI remains enabled as the control plane.</p>
    <label class="check"><input name="http_api_enabled" type="checkbox"{_checked_attr(config.http.api_enabled)}> Enable REST API</label>
    <label class="check"><input name="http_prometheus_enabled" type="checkbox"{_checked_attr(config.http.prometheus_enabled)}> Enable Prometheus metrics</label>
    <label class="check"><input name="http_homeassistant_enabled" type="checkbox"{_checked_attr(config.http.homeassistant_enabled)}> Enable Home Assistant discovery endpoint</label>
    <div class="grid">
      <label>Web listen address <input name="http_listen" value="{_escape(config.http.listen)}"></label>
      <label>Web port <input name="http_port" type="number" min="1" max="65535" value="{config.http.port}"></label>
    </div>
  </fieldset>

  <fieldset>
    <legend>MQTT</legend>
    <label class="check"><input name="mqtt_enabled" type="checkbox"{_checked_attr(config.mqtt.enabled)}> Enable MQTT publishing</label>
    <div class="grid">
      <label>Host <input name="mqtt_host" value="{_escape(config.mqtt.host)}"></label>
      <label>Port <input name="mqtt_port" type="number" min="1" max="65535" value="{config.mqtt.port}"></label>
      <label>Client ID <input name="mqtt_client_id" value="{_escape(config.mqtt.client_id)}"></label>
      <label>Topic prefix <input name="mqtt_topic_prefix" value="{_escape(config.mqtt.topic_prefix)}"></label>
      <label>Discovery prefix <input name="mqtt_discovery_prefix" value="{_escape(config.mqtt.discovery_prefix)}"></label>
      <label>Publish interval seconds <input name="mqtt_publish_interval_seconds" type="number" min="1" step="0.1" value="{_escape(str(config.mqtt.publish_interval_seconds))}"></label>
      <label>Username <input name="mqtt_username" value="{_escape(config.mqtt.username)}"></label>
      <label>Password <input name="mqtt_password" type="password" value="{_escape(config.mqtt.password)}"></label>
    </div>
  </fieldset>

  <fieldset>
    <legend>Logging</legend>
    <label>Level
      <select name="logging_level">
        {''.join(f'<option value="{level}"{_selected(config.logging.level.upper(), level)}>{level}</option>' for level in ["DEBUG", "INFO", "WARNING", "ERROR"])}
      </select>
    </label>
  </fieldset>

  <button type="submit">Save Configuration</button>
</form>"""


def render_message_page(title: str, message: str, config: AppConfig) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(title)} - PowerPi UPS Gateway</title>
  <style>body {{ font: 16px system-ui, sans-serif; margin: 2rem; max-width: 760px; }} a {{ color: #0969da; }}</style>
</head>
<body>
  <h1>{_escape(title)}</h1>
  <p>{_escape(message)}</p>
  <p><a href="/ui">Back to Web UI</a></p>
</body>
</html>
"""


def _field(form: dict[str, list[str]], name: str) -> str:
    values = form.get(name)
    if not values:
        return ""
    return values[0].strip()


def _checked(form: dict[str, list[str]], name: str) -> bool:
    return name in form


def _checked_attr(value: bool) -> str:
    return " checked" if value else ""


def _selected(value: str, expected: str) -> str:
    return " selected" if value == expected else ""


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

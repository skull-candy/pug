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
from pug.raw_stats import state_payload
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
                        render_dashboard_page(state.to_dict(), config).encode(),
                    )
                elif self.path == "/settings":
                    self._send(
                        200,
                        "text/html; charset=utf-8",
                        render_settings_page(config).encode(),
                    )
                elif self.path == "/logs":
                    self._send(
                        200,
                        "text/html; charset=utf-8",
                        render_logs_page(config, tail_log_lines(config.logging.file_path, config.logging.web_tail_lines)).encode(),
                    )
                elif self.path == "/api/state":
                    if config.http.api_enabled:
                        self._send_json(state_payload(state))
                    else:
                        self._send_json({"error": "api disabled"}, status=404)
                elif self.path == "/api/raw":
                    if config.http.api_enabled:
                        self._send_json(state.raw)
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
        logging=LoggingConfig(
            level=_field(form, "logging_level"),
            file_path=_field(form, "logging_file_path"),
            web_tail_lines=int(_field(form, "logging_web_tail_lines")),
        ),
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
        "logging": {
            "level": config.logging.level,
            "file_path": config.logging.file_path,
            "web_tail_lines": config.logging.web_tail_lines,
        },
    }


def render_control_page(state: dict[str, Any], config: AppConfig) -> str:
    return render_dashboard_page(state, config)


def render_dashboard_page(state: dict[str, Any], config: AppConfig) -> str:
    title = _escape(str(state["name"]))
    rows = render_detail_rows(state)
    raw_rows = "\n".join(
        f"<tr><th>{_escape(raw_display_label(str(key)))}</th><td>{_escape(str(value))}</td></tr>"
        for key, value in sorted(state.get("raw", {}).items())
    )
    overview = render_overview_cards(state)
    diagram = render_power_flow_diagram(state)
    return page_shell(
        title,
        "dashboard",
        f"""
        <section class="hero-panel">
          <div class="hero-head">
            <div>
              <h1>{title}</h1>
              <p class="muted">{_escape(display_value("status_text", state.get("status_text", "-")))}</p>
            </div>
            <span class="health {'ok' if state.get('online') else 'warn'}">{'Healthy' if state.get('online') else 'Attention'}</span>
          </div>
          {overview}
          {diagram}
        </section>

        <section>
          <div class="section-head">
            <h2>UPS Details</h2>
            <a class="text-link" href="/api/state">JSON</a>
          </div>
          <div class="detail-grid">{rows}</div>
        </section>

        <section>
          <div class="section-head">
            <h2>Raw Backend Stats</h2>
            <a class="text-link" href="/api/raw">Raw JSON</a>
          </div>
          <table>{raw_rows}</table>
        </section>
        """,
    )


def page_shell(title: str, active: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>{_escape(title)} - PowerPi UPS Gateway</title>
  <style>
    :root {{ color-scheme: light; --blue:#075eb5; --blue2:#0b73ce; --ink:#17202a; --muted:#667085; --line:#d7dee8; --bg:#f3f6fa; --card:#ffffff; --good:#16a34a; --warn:#d97706; --bad:#dc2626; }}
    * {{ box-sizing: border-box; }}
    body {{ font: 15px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; color: var(--ink); background: var(--bg); }}
    .topbar {{ position: sticky; top: 0; z-index: 5; display:flex; align-items:center; justify-content:space-between; gap:16px; padding: 12px 24px; border-bottom:1px solid var(--line); background: rgba(255,255,255,.94); backdrop-filter: blur(10px); }}
    .brand {{ font-weight: 800; color: var(--blue); text-decoration:none; }}
    nav {{ display:flex; gap:8px; flex-wrap:wrap; }}
    nav a, .button {{ display:inline-flex; align-items:center; justify-content:center; min-height:36px; padding:8px 12px; border-radius:7px; text-decoration:none; color:var(--ink); border:1px solid transparent; }}
    nav a.active {{ background:#eaf3ff; border-color:#bddcff; color:var(--blue); }}
    .button {{ background:var(--blue); color:#fff; border:0; }}
    .button.secondary {{ background:#eef2f7; color:var(--ink); }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 18px; }}
    section, .hero-panel {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 18px; margin: 0 0 16px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
    h1, h2 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 22px; }}
    h2 {{ font-size: 17px; }}
    .muted {{ color: var(--muted); margin: 4px 0 0; }}
    .hero-head, .section-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:16px; }}
    .health {{ display:inline-flex; align-items:center; gap:8px; padding:6px 10px; border-radius:999px; font-weight:700; }}
    .health.ok {{ color:var(--good); background:#ecfdf3; }}
    .health.warn {{ color:var(--warn); background:#fff7ed; }}
    .cards {{ display:grid; grid-template-columns: repeat(6, minmax(140px, 1fr)); gap: 10px; padding: 12px 0 18px; border-top:1px solid #edf1f5; border-bottom:1px solid #edf1f5; }}
    .metric {{ min-width:0; }}
    .metric-label {{ color:#344054; font-size:13px; margin-bottom:6px; }}
    .metric-value {{ font-weight:800; font-size:17px; color:#101828; overflow-wrap:anywhere; }}
    .metric-icon {{ color:var(--blue); font-weight:900; margin-right:6px; }}
    .diagram-wrap {{ overflow-x:auto; padding: 18px 0 2px; }}
    svg.power {{ width:100%; min-width:820px; height:360px; }}
    .path {{ stroke:#d8dee8; stroke-width:5; fill:none; stroke-linecap:round; stroke-linejoin:round; }}
    .path.active {{ stroke:var(--blue); stroke-dasharray:12 8; animation: dash 1.2s linear infinite; }}
    .path.standby {{ opacity:.55; }}
    .path.solid.active {{ stroke-dasharray:none; animation:none; }}
    .node {{ fill:#fff; stroke:#98a2b3; stroke-width:3; }}
    .node.standby {{ fill:#98a2b3; }}
    .node.active {{ stroke:var(--blue); filter: drop-shadow(0 2px 6px rgba(7,94,181,.20)); }}
    .node-fill {{ fill:#98a2b3; }}
    .node-fill.active {{ fill:var(--blue2); }}
    .node-text {{ font: 15px system-ui, sans-serif; fill:#111827; text-anchor:middle; font-weight:700; }}
    .node-small {{ font: 13px system-ui, sans-serif; fill:#344054; text-anchor:middle; }}
    .node-caption {{ font: 12px system-ui, sans-serif; fill:var(--muted); text-anchor:middle; }}
    .legend {{ display:flex; gap:14px; flex-wrap:wrap; color:var(--muted); font-size:13px; padding-top:8px; }}
    .legend span::before {{ content:""; display:inline-block; width:22px; height:4px; border-radius:4px; margin-right:6px; vertical-align:middle; background:#d8dee8; }}
    .legend .active-leg::before {{ background:var(--blue); }}
    .detail-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; }}
    .detail-item {{ border:1px solid #edf1f5; border-radius:8px; padding:10px 12px; background:#fbfcfe; }}
    .detail-item dt {{ color:var(--muted); font-size:13px; }}
    .detail-item dd {{ margin:4px 0 0; font-weight:700; overflow-wrap:anywhere; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #edf1f5; padding: .55rem; text-align: left; vertical-align:top; }}
    th {{ width: 18rem; color: #57606a; font-weight: 700; }}
    form {{ display: grid; gap: 16px; }}
    fieldset {{ border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
    legend {{ font-weight: 800; padding: 0 6px; }}
    label {{ display: grid; gap: 4px; margin: 10px 0; }}
    input, select {{ font: inherit; padding: 9px; border: 1px solid #afb8c1; border-radius: 6px; background:#fff; }}
    input[type="checkbox"] {{ width: 18px; height: 18px; }}
    .check {{ display: flex; align-items: center; gap: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px 18px; }}
    button {{ font: inherit; padding: 10px 14px; border: 0; border-radius: 6px; background: var(--blue); color: white; cursor: pointer; }}
    .hint {{ color: var(--muted); font-size: 14px; }}
    .text-link {{ color:var(--blue); text-decoration:none; font-weight:700; }}
    .log-view {{ max-height: 68vh; overflow:auto; padding:14px; background:#0b1220; color:#d8e2f1; border-radius:8px; font: 13px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; white-space:pre-wrap; }}
    @keyframes dash {{ to {{ stroke-dashoffset: -32; }} }}
    @media (max-width: 880px) {{ .cards {{ grid-template-columns: repeat(2, minmax(130px, 1fr)); }} .topbar {{ align-items:flex-start; flex-direction:column; }} }}
  </style>
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/ui">PowerPi UPS Gateway</a>
    <nav>
      <a class="{_active(active, 'dashboard')}" href="/ui">Dashboard</a>
      <a class="{_active(active, 'settings')}" href="/settings">Settings</a>
      <a class="{_active(active, 'logs')}" href="/logs">Logs</a>
      <a href="/metrics">Metrics</a>
    </nav>
  </header>
  <main>{content}</main>
</body>
</html>
"""


def render_overview_cards(state: dict[str, Any]) -> str:
    cards = [
        ("Mode", "online", "Line mode" if state.get("online") else "Battery/unknown"),
        ("Remaining Time", "runtime_minutes", display_value("runtime_minutes", state.get("runtime_minutes"))),
        ("Battery Capacity", "battery_charge_percent", display_value("battery_charge_percent", state.get("battery_charge_percent"))),
        ("Load", "load_percent", display_value("load_percent", state.get("load_percent"))),
        ("Battery Voltage", "battery_voltage", display_value("battery_voltage", state.get("battery_voltage"))),
        ("Self Test", "status_text", state.get("raw", {}).get("SELFTEST", "-")),
    ]
    html = []
    for label, icon_key, value in cards:
        html.append(
            f'<div class="metric"><div class="metric-label">{_escape(label)}</div>'
            f'<div class="metric-value"><span class="metric-icon">{metric_icon(icon_key)}</span>{_escape(str(value))}</div></div>'
        )
    return '<div class="cards">' + "".join(html) + "</div>"


def render_power_flow_diagram(state: dict[str, Any]) -> str:
    mode = power_flow_mode(state)
    line_active = " active" if mode == "line" else " standby"
    battery_active = " active" if mode == "battery" else " standby"
    bypass_active = " active" if mode == "bypass" else " standby"
    inverter_active = " active" if mode == "battery" else " standby"
    avr_active = " active" if mode in {"line", "online_conversion"} else " standby"
    input_v = display_value("input_voltage", state.get("input_voltage"))
    battery = display_value("battery_charge_percent", state.get("battery_charge_percent"))
    load = display_value("load_percent", state.get("load_percent"))
    output_v = display_value("output_voltage", state.get("output_voltage"))
    mode_label = {
        "line": "Line / AVR path active",
        "battery": "Battery path active",
        "bypass": "Bypass path active",
        "online_conversion": "Conversion path active",
        "unknown": "Power path unknown",
    }[mode]
    return f"""
    <div class="diagram-wrap">
      <svg class="power" viewBox="0 0 1040 360" role="img" aria-label="UPS power flow diagram">
        <path class="path{bypass_active}" d="M195 95 H835 V175" />
        <path class="path{line_active}" d="M155 175 H390" />
        <path class="path{line_active}" d="M510 175 H835" />
        <path class="path{battery_active}" d="M455 278 V222 H650 V175" />
        <path class="path{inverter_active}" d="M650 175 H835" />

        <g>
          <path d="M92 120 L126 120 L109 88 Z" fill="none" stroke="var(--blue)" stroke-width="4" />
          <line x1="109" y1="120" x2="109" y2="152" stroke="var(--blue)" stroke-width="4" />
          <text class="node-text" x="109" y="202">Input</text>
          <text class="node-small" x="109" y="222">{_escape(input_v)}</text>
        </g>

        <g>
          <rect class="node{avr_active}" x="390" y="125" width="120" height="100" rx="12" />
          <rect class="node-fill{avr_active}" x="413" y="149" width="74" height="24" rx="5" />
          <text x="450" y="167" fill="#fff" text-anchor="middle" font-size="16" font-weight="700">AVR</text>
          <text class="node-caption" x="450" y="195">Line conditioner</text>
          <text class="node-text" x="450" y="250">Line / AVR</text>
        </g>

        <g>
          <circle class="node{bypass_active}" cx="520" cy="95" r="34" />
          <text x="520" y="102" fill="#fff" text-anchor="middle" font-size="23">~</text>
          <text class="node-text" x="520" y="145">Bypass</text>
        </g>

        <g>
          <circle class="node{inverter_active}" cx="650" cy="175" r="38" />
          <text x="650" y="169" fill="#fff" text-anchor="middle" font-size="21">=</text>
          <text x="650" y="190" fill="#fff" text-anchor="middle" font-size="23">~</text>
          <text class="node-text" x="650" y="250">Inverter</text>
        </g>

        <g>
          <rect x="428" y="278" width="54" height="30" rx="4" fill="none" stroke="var(--blue)" stroke-width="4" />
          <rect x="482" y="287" width="7" height="12" rx="2" fill="var(--blue)" />
          <text class="node-text" x="455" y="335">Battery</text>
          <text class="node-small" x="455" y="323">{_escape(battery)}</text>
        </g>

        <g>
          <rect x="875" y="137" width="86" height="76" rx="10" fill="#f8fafc" stroke="var(--blue)" stroke-width="3" />
          <path d="M905 156 v37 m-10-25 h20 m-16 0 v-14 m12 14 v-14" fill="none" stroke="var(--blue)" stroke-width="4" stroke-linecap="round" />
          <text class="node-text" x="918" y="238">Load</text>
          <text class="node-small" x="918" y="258">{_escape(load)}</text>
          <text class="node-small" x="918" y="278">{_escape(output_v)}</text>
        </g>
      </svg>
      <div class="legend"><span class="active-leg">{_escape(mode_label)}</span><span>Standby path</span></div>
    </div>
    """


def power_flow_mode(state: dict[str, Any]) -> str:
    status = f"{state.get('status_text', '')} {state.get('raw', {}).get('STATUS', '')}".upper()
    if "BYPASS" in status:
        return "bypass"
    if state.get("on_battery"):
        return "battery"
    if state.get("online") and voltages_close(state.get("input_voltage"), state.get("output_voltage")):
        return "line"
    if state.get("online"):
        return "online_conversion"
    return "unknown"


def voltages_close(input_voltage: Any, output_voltage: Any, tolerance: float = 5.0) -> bool:
    try:
        return abs(float(input_voltage) - float(output_voltage)) <= tolerance
    except (TypeError, ValueError):
        return False


def render_detail_rows(state: dict[str, Any]) -> str:
    preferred = [
        "manufacturer",
        "model",
        "name",
        "serial",
        "firmware",
        "status_text",
        "online",
        "on_battery",
        "replace_battery",
        "battery_charge_percent",
        "runtime_minutes",
        "battery_voltage",
        "input_voltage",
        "output_voltage",
        "output_current",
        "line_frequency",
        "load_percent",
        "internal_temperature_c",
        "manufacture_date",
        "battery_date",
        "last_update",
        "source_backend",
    ]
    keys = [key for key in preferred if key in state]
    keys.extend(key for key in state if key not in keys and key != "raw")
    return "".join(
        f'<dl class="detail-item"><dt>{_escape(display_label(key))}</dt><dd>{_escape(display_value(key, state.get(key)))}</dd></dl>'
        for key in keys
    )


def tail_log_lines(path: str, max_lines: int) -> list[str]:
    if max_lines <= 0:
        return []
    log_path = Path(path)
    if not log_path.exists():
        return [f"Log file does not exist yet: {path}"]
    # Read from the end in bounded chunks so very large logs do not slow the UI.
    chunk_size = 8192
    data = b""
    with log_path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        while position > 0 and data.count(b"\n") <= max_lines:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            data = handle.read(read_size) + data
    return data.decode("utf-8", errors="replace").splitlines()[-max_lines:]


def metric_icon(key: str) -> str:
    return {
        "online": "[~]",
        "runtime_minutes": "[t]",
        "battery_charge_percent": "[b]",
        "load_percent": "[L]",
        "battery_voltage": "[V]",
        "status_text": "[i]",
    }.get(key, "[ ]")


def _active(active: str, page: str) -> str:
    return "active" if active == page else ""


def render_settings_page(config: AppConfig) -> str:
    return page_shell(
        "Settings",
        "settings",
        f"""
        <section>
          <h1>Settings</h1>
          <p class="muted">Save writes config.yaml. Restart the service to apply backend, listener, SNMP, and MQTT runtime changes.</p>
          {render_config_form(config)}
        </section>
        """,
    )


def render_logs_page(config: AppConfig, lines: list[str]) -> str:
    log_lines = "\n".join(_escape(line.rstrip("\n")) for line in lines)
    return page_shell(
        "Logs",
        "logs",
        f"""
        <section>
          <div class="section-head">
            <div>
              <h1>Logs</h1>
              <p class="muted">Showing the last {config.logging.web_tail_lines} lines from {_escape(config.logging.file_path)}.</p>
            </div>
            <a class="button secondary" href="/logs">Refresh</a>
          </div>
          <pre class="log-view">{log_lines or 'No log lines available.'}</pre>
        </section>
        """,
    )


DISPLAY_LABELS = {
    "manufacturer": "Manufacturer",
    "model": "Model",
    "name": "UPS Name",
    "serial": "Serial Number",
    "firmware": "Firmware",
    "manufacture_date": "Manufacture Date",
    "battery_date": "Battery Date",
    "status_text": "UPS Status",
    "online": "Online",
    "on_battery": "On Battery",
    "replace_battery": "Replace Battery",
    "battery_charge_percent": "Battery Charge",
    "runtime_minutes": "Runtime Remaining",
    "seconds_on_battery": "Seconds on Battery",
    "battery_voltage": "Battery Voltage",
    "input_voltage": "Input Voltage",
    "output_voltage": "Output Voltage",
    "output_current": "Output Current",
    "line_frequency": "Line Frequency",
    "load_percent": "Load",
    "load_va_percent": "Load VA",
    "internal_temperature_c": "Internal Temperature",
    "nominal_output_voltage": "Nominal Output Voltage",
    "nominal_power_watts": "Nominal Power",
    "nominal_va": "Nominal VA",
    "min_battery_charge_percent": "Minimum Battery Charge",
    "min_runtime_minutes": "Minimum Runtime",
    "last_update": "Last Update",
    "source_backend": "Source Backend",
}

RAW_LABELS = {
    "APC": "APC Protocol",
    "DATE": "Sample Time",
    "HOSTNAME": "Host Name",
    "VERSION": "APCUPSD Version",
    "UPSNAME": "UPS Name",
    "CABLE": "Cable",
    "DRIVER": "Driver",
    "UPSMODE": "UPS Mode",
    "STARTTIME": "APCUPSD Start Time",
    "MODEL": "Model",
    "STATUS": "UPS Status",
    "LINEV": "Input Voltage",
    "LOADPCT": "Load",
    "LOADAPNT": "Load Apparent",
    "BCHARGE": "Battery Charge",
    "TIMELEFT": "Runtime Remaining",
    "MBATTCHG": "Minimum Battery Charge",
    "MINTIMEL": "Minimum Runtime",
    "MAXTIME": "Maximum Runtime",
    "OUTPUTV": "Output Voltage",
    "DWAKE": "Wake Delay",
    "DSHUTD": "Shutdown Delay",
    "ITEMP": "Internal Temperature",
    "BATTV": "Battery Voltage",
    "LINEFREQ": "Line Frequency",
    "OUTCURNT": "Output Current",
    "LASTXFER": "Last Transfer Reason",
    "NUMXFERS": "Transfer Count",
    "XONBATT": "Last On Battery Time",
    "TONBATT": "Time on Battery",
    "CUMONBATT": "Cumulative Time on Battery",
    "XOFFBATT": "Last Off Battery Time",
    "SELFTEST": "Self Test",
    "STATFLAG": "Status Flag",
    "MANDATE": "Manufacture Date",
    "SERIALNO": "Serial Number",
    "BATTDATE": "Battery Date",
    "NOMOUTV": "Nominal Output Voltage",
    "NOMPOWER": "Nominal Power",
    "NOMAPNT": "Nominal Apparent Power",
    "FIRMWARE": "Firmware",
    "END APC": "APC Sample End",
}

VALUE_UNITS = {
    "battery_charge_percent": "%",
    "runtime_minutes": " min",
    "seconds_on_battery": " sec",
    "battery_voltage": " V",
    "input_voltage": " V",
    "output_voltage": " V",
    "output_current": " A",
    "line_frequency": " Hz",
    "load_percent": "%",
    "load_va_percent": "%",
    "internal_temperature_c": " C",
    "nominal_output_voltage": " V",
    "nominal_power_watts": " W",
    "nominal_va": " VA",
    "min_battery_charge_percent": "%",
    "min_runtime_minutes": " min",
}


def display_label(key: str) -> str:
    return DISPLAY_LABELS.get(key, key.replace("_", " ").title())


def raw_display_label(key: str) -> str:
    return RAW_LABELS.get(key, key.replace("_", " ").title())


def display_value(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value in {"", None}:
        return "-"
    if key == "last_update":
        return str(value).replace("T", " ").replace("+00:00", " UTC")
    unit = VALUE_UNITS.get(key)
    if unit:
        return f"{value}{unit}"
    return str(value)


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
    <div class="grid">
      <label>Level
        <select name="logging_level">
          {''.join(f'<option value="{level}"{_selected(config.logging.level.upper(), level)}>{level}</option>' for level in ["DEBUG", "INFO", "WARNING", "ERROR"])}
        </select>
      </label>
      <label>Log file path <input name="logging_file_path" value="{_escape(config.logging.file_path)}"></label>
      <label>Web log tail lines <input name="logging_web_tail_lines" type="number" min="1" value="{config.logging.web_tail_lines}"></label>
    </div>
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

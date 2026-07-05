from __future__ import annotations

import json
import logging
from datetime import datetime
from importlib.resources import files
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any
from urllib.parse import parse_qs

from pug import __version__
from pug.config import (
    AppConfig,
    BackendConfig,
    ConfigError,
    DiagnosticsConfig,
    HttpConfig,
    LoggingConfig,
    MqttConfig,
    SnmpConfig,
    UpdateConfig,
    format_command,
    load_config,
    parse_command,
    save_config,
    validate_config,
)
from pug.diagnostics import DiagnosticManager, DiagnosticSnapshot, diagnostic_label
from pug.frontends.homeassistant import discovery_payloads
from pug.frontends.mqtt import publish_homeassistant_rediscovery
from pug.frontends.prometheus import render_metrics
from pug.raw_stats import state_payload
from pug.state import StateStore
from pug.updater import SERVICE_NAME, UpdateManager, UpdateSnapshot, restart_service_later

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
        self.diagnostics = DiagnosticManager()
        self.updater = UpdateManager(self.config_path, config)

    def serve_forever(self, stop: Event) -> None:
        handler = self._handler()
        server = ThreadingHTTPServer((self.listen, self.port), handler)
        server.timeout = 1
        update_thread = Thread(
            target=self.updater.run_background_checks,
            args=(stop,),
            name="update-checker",
            daemon=True,
        )
        update_thread.start()
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
                if self.path.startswith("/assets/ups-icons/"):
                    asset = read_ups_icon(self.path.rsplit("/", 1)[-1])
                    if asset is None:
                        self._send_json({"error": "not found"}, status=404)
                    else:
                        self._send(200, "image/png", asset)
                elif self.path in {"/", "/ui"}:
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
                        render_logs_page(
                            config,
                            tail_log_lines(config.logging.file_path, config.logging.web_tail_lines),
                            tail_log_lines(config.logging.apcupsd_events_path, config.logging.web_tail_lines),
                        ).encode(),
                    )
                elif self.path == "/diagnostics":
                    self._send(
                        200,
                        "text/html; charset=utf-8",
                        render_diagnostics_page(state.to_dict(), config, frontend.diagnostics.snapshot()).encode(),
                    )
                elif self.path == "/updates":
                    self._send(
                        200,
                        "text/html; charset=utf-8",
                        render_updates_page(frontend.updater.snapshot()).encode(),
                    )
                elif self.path == "/raw":
                    self._send(
                        200,
                        "text/html; charset=utf-8",
                        render_raw_stats_page(state.to_dict(), config).encode(),
                    )
                elif self.path == "/ui/live/dashboard":
                    self._send_json(dashboard_live_payload(state.to_dict()))
                elif self.path == "/ui/live/raw":
                    self._send_json(raw_live_payload(state.to_dict()))
                elif self.path == "/ui/live/logs":
                    self._send_json(logs_live_payload(config))
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
                elif self.path == "/api/diagnostics":
                    self._send_json(diagnostics_api_payload(state.to_dict(), frontend.diagnostics.snapshot()))
                elif self.path == "/api/updates":
                    self._send_json(frontend.updater.snapshot().to_dict())
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
                if self.path == "/api/diagnostics/start":
                    length = int(self.headers.get("Content-Length", "0"))
                    body = self.rfile.read(length).decode("utf-8")
                    form = parse_qs(body, keep_blank_values=True)
                    config = frontend.current_config()
                    try:
                        started = frontend.diagnostics.start(_field(form, "action"), config.diagnostics)
                        self._send_json(
                            {
                                "ok": started,
                                "message": "Diagnostic started." if started else "Another diagnostic is already running.",
                                "diagnostic": frontend.diagnostics.snapshot().to_dict(),
                            }
                        )
                    except ValueError as exc:
                        self._send_json({"ok": False, "message": str(exc)}, status=400)
                    return
                if self.path == "/api/updates/check":
                    frontend.updater.check_if_due()
                    self._send_json(frontend.updater.snapshot().to_dict())
                    return
                if self.path == "/api/updates/install":
                    started = frontend.updater.start_install()
                    self._send_json(
                        {
                            "ok": started,
                            "message": "Update install started." if started else "Update install already running.",
                            "update": frontend.updater.snapshot().to_dict(),
                        }
                    )
                    return
                if self.path == "/homeassistant/rediscover":
                    config = frontend.current_config()
                    if not config.mqtt.enabled:
                        self._send_json({"ok": False, "message": "MQTT publishing is disabled in Settings."}, status=400)
                        return
                    try:
                        publish_homeassistant_rediscovery(config.mqtt, store.get())
                    except OSError as exc:
                        LOGGER.exception("Home Assistant rediscovery publish failed")
                        self._send_json({"ok": False, "message": str(exc)}, status=502)
                        return
                    self._send_json({"ok": True, "message": "Home Assistant MQTT discovery was republished."})
                    return
                if self.path != "/config":
                    self._send_json({"error": "not found"}, status=404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                form = parse_qs(body, keep_blank_values=True)
                try:
                    config = config_from_form(form, frontend.current_config())
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
                        f"Settings were saved. Restarting the {SERVICE_NAME} service to apply runtime changes.",
                        config,
                    ).encode(),
                )
                schedule_service_restart()

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


def schedule_service_restart() -> None:
    Thread(target=restart_service_later, name="config-service-restarter", daemon=True).start()


def config_from_form(form: dict[str, list[str]], current_config: AppConfig | None = None) -> AppConfig:
    update_defaults = current_config.update if current_config else UpdateConfig()
    update_gitlab_base_url = _field(form, "update_gitlab_base_url") or update_defaults.gitlab_base_url
    update_project_path = _field(form, "update_project_path") or update_defaults.project_path
    if update_gitlab_base_url != update_defaults.gitlab_base_url or update_project_path != update_defaults.project_path:
        update_defaults = UpdateConfig(gitlab_base_url=update_gitlab_base_url, project_path=update_project_path)
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
            apcupsd_events_path=_field(form, "logging_apcupsd_events_path"),
            web_tail_lines=int(_field(form, "logging_web_tail_lines")),
        ),
        diagnostics=DiagnosticsConfig(
            before_command=parse_command(_field(form, "diagnostics_before_command")),
            after_command=parse_command(_field(form, "diagnostics_after_command")),
            self_test_command=parse_command(_field(form, "diagnostics_self_test_command")),
            self_test_selection=_field(form, "diagnostics_self_test_selection"),
            battery_calibration_command=parse_command(_field(form, "diagnostics_battery_calibration_command")),
            battery_calibration_selection=_field(form, "diagnostics_battery_calibration_selection"),
            command_timeout_seconds=int(_field(form, "diagnostics_command_timeout_seconds")),
        ),
        update=UpdateConfig(
            gitlab_base_url=update_gitlab_base_url,
            project_path=update_project_path,
            check_interval=_field(form, "update_check_interval") or update_defaults.check_interval,
            last_update_check=update_defaults.last_update_check,
            latest_version=update_defaults.latest_version,
            latest_release_url=update_defaults.latest_release_url,
            latest_release_name=update_defaults.latest_release_name,
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
            "apcupsd_events_path": config.logging.apcupsd_events_path,
            "web_tail_lines": config.logging.web_tail_lines,
        },
        "diagnostics": {
            "before_command": config.diagnostics.before_command,
            "after_command": config.diagnostics.after_command,
            "self_test_command": config.diagnostics.self_test_command,
            "self_test_selection": config.diagnostics.self_test_selection,
            "battery_calibration_command": config.diagnostics.battery_calibration_command,
            "battery_calibration_selection": config.diagnostics.battery_calibration_selection,
            "command_timeout_seconds": config.diagnostics.command_timeout_seconds,
        },
        "update": {
            "gitlab_base_url": config.update.gitlab_base_url,
            "project_path": config.update.project_path,
            "check_interval": config.update.check_interval,
            "last_update_check": config.update.last_update_check,
            "latest_version": config.update.latest_version,
            "latest_release_url": config.update.latest_release_url,
            "latest_release_name": config.update.latest_release_name,
        },
    }


def diagnostics_api_payload(state: dict[str, Any], diagnostic: DiagnosticSnapshot) -> dict[str, Any]:
    return {"state": state, "diagnostic": diagnostic.to_dict(), "summary": diagnostic_summary(state, diagnostic)}


def dashboard_live_payload(state: dict[str, Any]) -> dict[str, str]:
    return {
        "title": str(state.get("name", "PowerPi UPS")),
        "status": display_value("status_text", state.get("status_text", "-")),
        "health_text": "Healthy" if state.get("online") else "Attention",
        "health_class": "ok" if state.get("online") else "warn",
        "overview": render_overview_cards(state),
        "diagram": render_power_flow_diagram(state),
        "details": render_detail_rows(state),
    }


def raw_live_payload(state: dict[str, Any]) -> dict[str, str]:
    return {"rows": render_raw_rows(state)}


def logs_live_payload(config: AppConfig) -> dict[str, list[str]]:
    return {
        "pug": tail_log_lines(config.logging.file_path, config.logging.web_tail_lines),
        "apcupsd": tail_log_lines(config.logging.apcupsd_events_path, config.logging.web_tail_lines),
    }


def read_ups_icon(filename: str) -> bytes | None:
    allowed = {"input.png", "avr.png", "bypass.png", "inverter.png", "battery.png", "load.png"}
    if filename not in allowed:
        return None
    try:
        return files("pug").joinpath("assets", "ups-icons", filename).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError):
        LOGGER.warning("UPS icon asset is missing: %s", filename)
        return None


def render_control_page(state: dict[str, Any], config: AppConfig) -> str:
    return render_dashboard_page(state, config)


def render_dashboard_page(state: dict[str, Any], config: AppConfig) -> str:
    title = _escape(str(state["name"]))
    rows = render_detail_rows(state)
    overview = render_overview_cards(state)
    diagram = render_power_flow_diagram(state)
    return page_shell(
        title,
        "dashboard",
        f"""
        <section class="hero-panel">
          <div class="hero-head">
            <div>
              <h1 id="dashboard-title">{title}</h1>
              <p id="dashboard-status" class="muted">{_escape(display_value("status_text", state.get("status_text", "-")))}</p>
            </div>
            <span id="dashboard-health" class="health {'ok' if state.get('online') else 'warn'}">{'Healthy' if state.get('online') else 'Attention'}</span>
          </div>
          <div id="dashboard-overview">{overview}</div>
          <div id="dashboard-diagram">{diagram}</div>
        </section>

        <section>
          <div class="section-head">
            <h2>UPS Details</h2>
            <a class="text-link" href="/api/state">JSON</a>
          </div>
          <div id="dashboard-details" class="detail-grid compact-details">{rows}</div>
        </section>
        <script>
        (() => {{
          const setText = (id, value) => {{
            const node = document.getElementById(id);
            if (node) node.textContent = value;
          }};
          const refresh = async () => {{
            const response = await fetch("/ui/live/dashboard", {{ cache: "no-store" }});
            if (!response.ok) return;
            const payload = await response.json();
            setText("dashboard-title", payload.title);
            setText("dashboard-status", payload.status);
            const health = document.getElementById("dashboard-health");
            if (health) {{
              health.textContent = payload.health_text;
              health.className = `health ${{payload.health_class}}`;
            }}
            document.getElementById("dashboard-overview").innerHTML = payload.overview;
            document.getElementById("dashboard-diagram").innerHTML = payload.diagram;
            document.getElementById("dashboard-details").innerHTML = payload.details;
          }};
          setInterval(refresh, 3000);
        }})();
        </script>
        """,
    )


def render_raw_stats_page(state: dict[str, Any], config: AppConfig) -> str:
    raw_rows = render_raw_rows(state)
    return page_shell(
        "Raw Backend Stats",
        "raw",
        f"""
        <section>
          <div class="section-head">
            <div>
              <h1>Raw Backend Stats</h1>
              <p class="muted">Raw values from the active UPS backend.</p>
            </div>
            <a class="text-link" href="/api/raw">Raw JSON</a>
          </div>
          <table><tbody id="raw-stats-rows">{raw_rows}</tbody></table>
        </section>
        <script>
        (() => {{
          const refresh = async () => {{
            const response = await fetch("/ui/live/raw", {{ cache: "no-store" }});
            if (!response.ok) return;
            const payload = await response.json();
            document.getElementById("raw-stats-rows").innerHTML = payload.rows;
          }};
          setInterval(refresh, 3000);
        }})();
        </script>
        """,
    )


def render_raw_rows(state: dict[str, Any]) -> str:
    raw_rows = "\n".join(
        f"<tr><th>{_escape(raw_display_label(str(key)))}</th><td>{_escape(str(value))}</td></tr>"
        for key, value in sorted(state.get("raw", {}).items())
    )
    if not raw_rows:
        return '<tr><td colspan="2" class="muted">No raw backend stats are available yet.</td></tr>'
    return raw_rows


def page_shell(title: str, active: str, content: str, auto_refresh: bool = False) -> str:
    refresh = '<meta http-equiv="refresh" content="30">' if auto_refresh else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh}
  <title>{_escape(title)} - PowerPi UPS Gateway</title>
  <style>
    :root {{ color-scheme: light; --blue:#075eb5; --blue2:#0b73ce; --ink:#17202a; --muted:#667085; --line:#d7dee8; --bg:#f3f6fa; --card:#ffffff; --good:#16a34a; --warn:#d97706; --bad:#dc2626; }}
    * {{ box-sizing: border-box; }}
    body {{ font: 15px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; color: var(--ink); background: var(--bg); }}
    .topbar {{ position: sticky; top: 0; z-index: 5; display:flex; align-items:center; justify-content:space-between; gap:16px; padding: 12px 24px; border-bottom:1px solid var(--line); background: rgba(255,255,255,.94); backdrop-filter: blur(10px); }}
    .update-banner {{ display:none; align-items:center; justify-content:space-between; gap:12px; padding:10px 24px; background:#fff7ed; border-bottom:1px solid #fed7aa; color:#9a3412; font-weight:700; }}
    .update-banner.show {{ display:flex; }}
    .update-banner a {{ color:#9a3412; }}
    .brand {{ font-weight: 800; color: var(--blue); text-decoration:none; }}
    nav {{ display:flex; gap:8px; flex-wrap:wrap; }}
    nav a, .button, .admin-button {{ display:inline-flex; align-items:center; justify-content:center; min-height:36px; padding:8px 12px; border-radius:7px; text-decoration:none; color:var(--ink); border:1px solid transparent; background:transparent; }}
    nav a.active {{ background:#eaf3ff; border-color:#bddcff; color:var(--blue); }}
    .admin-menu {{ position:relative; }}
    .admin-button {{ cursor:pointer; }}
    .admin-panel {{ display:none; position:absolute; right:0; top:42px; min-width:210px; padding:8px; border:1px solid var(--line); border-radius:8px; background:#fff; box-shadow:0 12px 28px rgba(16,24,40,.16); z-index:10; }}
    .admin-menu:hover .admin-panel, .admin-menu:focus-within .admin-panel {{ display:grid; gap:4px; }}
    .admin-panel a {{ justify-content:flex-start; }}
    .admin-button.active {{ background:#eaf3ff; border-color:#bddcff; color:var(--blue); }}
    .button {{ background:var(--blue); color:#fff; border:0; }}
    .button.secondary {{ background:#eef2f7; color:var(--ink); }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 18px; min-height:calc(100vh - 112px); }}
    .footer {{ display:flex; align-items:center; justify-content:space-between; gap:16px; padding:12px 24px; color:var(--muted); border-top:1px solid var(--line); background:#fff; font-size:13px; }}
    section, .hero-panel {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 18px; margin: 0 0 16px; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
    h1, h2 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 22px; }}
    h2 {{ font-size: 17px; }}
    .muted {{ color: var(--muted); margin: 4px 0 0; }}
    .hero-head, .section-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:16px; }}
    .health {{ display:inline-flex; align-items:center; gap:8px; padding:6px 10px; border-radius:999px; font-weight:700; }}
    .health.ok {{ color:var(--good); background:#ecfdf3; }}
    .health.warn {{ color:var(--warn); background:#fff7ed; }}
    .cards {{ display:grid; grid-template-columns: repeat(7, minmax(128px, 1fr)); gap: 10px; padding: 12px 0 18px; border-top:1px solid #edf1f5; border-bottom:1px solid #edf1f5; }}
    .metric {{ min-width:0; }}
    .metric-label {{ color:#344054; font-size:13px; margin-bottom:6px; }}
    .metric-value {{ font-weight:800; font-size:17px; color:#101828; overflow-wrap:anywhere; }}
    .metric-icon {{ display:inline-flex; width:20px; height:20px; margin-right:7px; vertical-align:-4px; }}
    .metric-icon img {{ display:block; width:20px; height:20px; object-fit:contain; }}
    .diagram-wrap {{ padding: 18px 0 2px; }}
    .diagram-card {{ border:1px solid #e1e7ef; border-radius:8px; background:#fff; padding:12px; overflow:hidden; }}
    svg.power {{ display:block; width:100%; height:auto; }}
    svg.power.mobile {{ display:none; }}
    .path {{ stroke:#d8dee8; stroke-width:5; fill:none; stroke-linecap:round; stroke-linejoin:round; }}
    .path.active {{ stroke:var(--blue); stroke-dasharray:none; filter: drop-shadow(0 1px 3px rgba(7,94,181,.22)); }}
    .path.bypass-active {{ stroke:var(--good); }}
    .path.standby {{ stroke:#c8d1dd; stroke-dasharray:9 9; opacity:.82; }}
    .path.inactive {{ stroke:#e3e8f0; stroke-dasharray:8 10; opacity:.9; }}
    .arrow {{ fill:var(--blue); }}
    .arrow.bypass-active {{ fill:var(--good); }}
    .node {{ fill:#fff; stroke:#98a2b3; stroke-width:2.5; }}
    .node.active {{ stroke:var(--blue); filter: drop-shadow(0 2px 6px rgba(7,94,181,.18)); }}
    .node.bypass-active {{ stroke:var(--good); filter: drop-shadow(0 2px 6px rgba(22,163,74,.18)); }}
    .node-fill {{ fill:#98a2b3; }}
    .node-fill.active {{ fill:var(--blue2); }}
    .node-fill.bypass-active {{ fill:var(--good); }}
    .node-icon {{ fill:none; stroke:var(--blue); stroke-width:3; stroke-linecap:round; stroke-linejoin:round; }}
    .node-icon.good {{ stroke:var(--good); }}
    .node-icon.muted {{ stroke:#98a2b3; }}
    .node-image {{ opacity:1; }}
    .node-image.muted {{ opacity:.42; filter: grayscale(1); }}
    .node-text {{ font: 15px system-ui, sans-serif; fill:#111827; text-anchor:middle; font-weight:800; }}
    .node-small {{ font: 13px system-ui, sans-serif; fill:#344054; text-anchor:middle; }}
    .node-caption {{ font: 12px system-ui, sans-serif; fill:var(--muted); text-anchor:middle; }}
    .path-label {{ font: 15px system-ui, sans-serif; fill:var(--blue); text-anchor:middle; font-weight:800; }}
    .path-label.good {{ fill:var(--good); }}
    .legend {{ display:flex; gap:14px; flex-wrap:wrap; color:var(--muted); font-size:13px; padding-top:10px; }}
    .legend span::before {{ content:""; display:inline-block; width:24px; height:4px; border-radius:4px; margin-right:6px; vertical-align:middle; background:#d8dee8; }}
    .legend .active-leg::before {{ background:var(--blue); }}
    .legend .bypass-leg::before {{ background:var(--good); }}
    .legend .inactive-leg::before {{ background:#c8d1dd; }}
    .detail-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 8px; }}
    .detail-item {{ border:1px solid #edf1f5; border-radius:8px; padding:8px 10px; background:#fbfcfe; min-height:58px; }}
    .detail-item dt {{ color:var(--muted); font-size:12px; line-height:1.25; }}
    .detail-item dd {{ margin:3px 0 0; font-weight:700; line-height:1.25; overflow-wrap:anywhere; }}
    .compact-details {{ grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0; }}
    .compact-details .detail-item {{ min-height:0; padding:3px 6px; border-radius:0; }}
    .compact-details .detail-item dt {{ font-size:11px; line-height:1.15; }}
    .compact-details .detail-item dd {{ margin-top:1px; font-size:13px; line-height:1.15; font-weight:700; }}
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
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
    .diagnostic-status {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:8px; margin:12px 0; }}
    .switch-row {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin:14px 0 10px; }}
    .switch {{ position:relative; display:inline-flex; align-items:center; gap:10px; cursor:pointer; font-weight:700; }}
    .switch input {{ position:absolute; opacity:0; width:1px; height:1px; }}
    .slider {{ width:44px; height:24px; border-radius:999px; background:#cbd5e1; position:relative; transition:.2s; }}
    .slider::after {{ content:""; position:absolute; width:18px; height:18px; top:3px; left:3px; border-radius:50%; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.25); transition:.2s; }}
    .switch input:checked + .slider {{ background:var(--blue); }}
    .switch input:checked + .slider::after {{ transform:translateX(20px); }}
    .hidden {{ display:none; }}
    .danger {{ background:var(--bad); color:#fff; }}
    @keyframes dash {{ to {{ stroke-dashoffset: -32; }} }}
    @media (max-width: 980px) {{ .cards {{ grid-template-columns: repeat(3, minmax(130px, 1fr)); }} }}
    @media (max-width: 700px) {{ main {{ padding:12px; }} section, .hero-panel {{ padding:14px; }} .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .topbar {{ align-items:flex-start; flex-direction:column; }} .update-banner {{ align-items:flex-start; flex-direction:column; }} .admin-panel {{ left:0; right:auto; }} .footer {{ align-items:flex-start; flex-direction:column; }} svg.power.desktop {{ display:none; }} svg.power.mobile {{ display:block; }} .diagram-card {{ padding:8px; }} }}
  </style>
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/ui">PowerPi UPS Gateway</a>
    <nav>
      <a class="{_active(active, 'dashboard')}" href="/ui">Dashboard</a>
      <div class="admin-menu">
        <button class="admin-button {_admin_active(active)}" type="button">Administration</button>
        <div class="admin-panel">
          <a class="{_active(active, 'raw')}" href="/raw">Raw Stats</a>
          <a class="{_active(active, 'diagnostics')}" href="/diagnostics">Diagnostics</a>
          <a class="{_active(active, 'settings')}" href="/settings">Settings</a>
          <a class="{_active(active, 'logs')}" href="/logs">Logs</a>
          <a class="{_active(active, 'updates')}" href="/updates">Updates</a>
          <a href="/metrics">Metrics</a>
        </div>
      </div>
    </nav>
  </header>
  <div id="update-banner" class="update-banner">
    <span id="update-banner-text"></span>
    <a id="update-banner-link" href="/updates">Open Release</a>
  </div>
  <main>{content}</main>
  <footer class="footer">
    <span>Copyright &copy; {datetime.now().year} PowerPi UPS Gateway. Developed By: Ahsan Muhammad</span>
    <span>Version {__version__}</span>
  </footer>
  <script>
  (() => {{
    const banner = document.getElementById("update-banner");
    const bannerText = document.getElementById("update-banner-text");
    const bannerLink = document.getElementById("update-banner-link");
    const refreshUpdateBanner = async () => {{
      try {{
        const response = await fetch("/api/updates", {{ cache: "no-store" }});
        if (!response.ok) return;
        const payload = await response.json();
        const show = Boolean(payload.update_available);
        banner.classList.toggle("show", show);
        if (show) {{
          bannerText.textContent = `New version available: ${{payload.latest_version}}. Installed: ${{payload.installed_version}}.`;
          bannerLink.href = payload.latest_release_url || "/updates";
        }}
      }} catch (error) {{}}
    }};
    refreshUpdateBanner();
    setInterval(refreshUpdateBanner, 60000);
  }})();
  </script>
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
        ("Input Voltage", "input_voltage", display_value("input_voltage", state.get("input_voltage"))),
        ("Output Voltage", "output_voltage", display_value("output_voltage", state.get("output_voltage"))),
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
    line_active = " active" if mode in {"line", "online_conversion"} else " inactive"
    battery_active = " active" if mode == "battery" else " inactive"
    bypass_active = " bypass-active" if mode == "bypass" else " standby"
    inverter_active = " active" if mode in {"line", "battery", "online_conversion"} else " inactive"
    avr_active = " active" if mode in {"line", "online_conversion"} else " standby"
    input_node = line_active if mode in {"line", "online_conversion"} else bypass_active if mode == "bypass" else " inactive"
    input_icon = "" if mode in {"line", "online_conversion", "bypass"} else " muted"
    avr_icon = "" if mode in {"line", "online_conversion"} else " muted"
    battery_icon = "" if mode == "battery" else " muted"
    inverter_icon = "" if mode in {"line", "battery", "online_conversion"} else " muted"
    load_icon = " good" if mode == "bypass" else inverter_icon
    line_marker = "arrow-blue" if mode in {"line", "online_conversion"} else "arrow-muted"
    battery_marker = "arrow-blue" if mode == "battery" else "arrow-muted"
    inverter_marker = "arrow-blue" if mode in {"line", "battery", "online_conversion"} else "arrow-muted"
    bypass_marker = "arrow-green" if mode == "bypass" else "arrow-muted"
    mobile_line_marker = "m-arrow-blue" if mode in {"line", "online_conversion"} else "m-arrow-muted"
    mobile_battery_marker = "m-arrow-blue" if mode == "battery" else "m-arrow-muted"
    mobile_inverter_marker = "m-arrow-blue" if mode in {"line", "battery", "online_conversion"} else "m-arrow-muted"
    mobile_bypass_marker = "m-arrow-green" if mode == "bypass" else "m-arrow-muted"
    input_v = display_value("input_voltage", state.get("input_voltage"))
    battery = display_value("battery_charge_percent", state.get("battery_charge_percent"))
    battery_v = display_value("battery_voltage", state.get("battery_voltage"))
    load = display_value("load_percent", state.get("load_percent"))
    output_v = display_value("output_voltage", state.get("output_voltage"))
    active_path_class = "bypass-leg" if mode == "bypass" else "active-leg"
    mode_label = {
        "line": "Line / AVR path active",
        "battery": "Battery path active",
        "bypass": "Bypass path active",
        "online_conversion": "Conversion path active",
        "unknown": "Power path unknown",
    }[mode]
    return f"""
    <div class="diagram-wrap">
      <div class="diagram-card">
        <svg class="power desktop" viewBox="0 0 1040 430" role="img" aria-label="UPS power flow diagram">
          <defs>
            <marker id="arrow-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path class="arrow" d="M0 0 L10 5 L0 10 Z" />
            </marker>
            <marker id="arrow-green" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path class="arrow bypass-active" d="M0 0 L10 5 L0 10 Z" />
            </marker>
            <marker id="arrow-muted" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path fill="#c8d1dd" d="M0 0 L10 5 L0 10 Z" />
            </marker>
          </defs>

          <path class="path{bypass_active}" marker-end="url(#{bypass_marker})" d="M110 224 C180 224 180 108 250 108 H795 C870 108 870 224 928 224" />
          <path class="path{line_active}" marker-end="url(#{line_marker})" d="M138 224 H310" />
          <path class="path{line_active}" marker-end="url(#{line_marker})" d="M430 224 H615" />
          <path class="path{inverter_active}" marker-end="url(#{inverter_marker})" d="M735 224 H920" />
          <path class="path{battery_active}" marker-end="url(#{battery_marker})" d="M450 336 V274 H675 V224" />

          <text class="path-label{' good' if mode == 'bypass' else ''}" x="520" y="76">{_escape(mode_label)}</text>
          <text class="node-text" x="520" y="98">Bypass Path</text>
          <text class="node-caption" x="520" y="118">{'Active' if mode == 'bypass' else 'Standby'}</text>

          <g>
            <circle class="node{input_node}" cx="100" cy="224" r="34" />
            <image class="node-image{input_icon}" href="/assets/ups-icons/input.png" x="74" y="198" width="52" height="52" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="100" y="276">Input</text>
            <text class="node-small" x="100" y="298">{_escape(input_v)}</text>
          </g>

          <g>
            <rect class="node{avr_active}" x="310" y="184" width="120" height="80" rx="10" />
            <image class="node-image{avr_icon}" href="/assets/ups-icons/avr.png" x="340" y="199" width="60" height="50" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="370" y="292">AVR</text>
            <text class="node-caption" x="370" y="314">Line conditioner</text>
          </g>

          <g>
            <rect class="node{bypass_active}" x="492" y="132" width="56" height="56" rx="8" />
            <image class="node-image{' ' if mode == 'bypass' else ' muted'}" href="/assets/ups-icons/bypass.png" x="504" y="144" width="32" height="32" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="520" y="212">Bypass</text>
          </g>

          <g>
            <rect class="node{inverter_active}" x="615" y="184" width="120" height="80" rx="10" />
            <image class="node-image{inverter_icon}" href="/assets/ups-icons/inverter.png" x="645" y="199" width="60" height="50" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="675" y="292">Inverter</text>
          </g>

          <g>
            <rect class="node{battery_active}" x="420" y="336" width="60" height="48" rx="7" />
            <image class="node-image{battery_icon}" href="/assets/ups-icons/battery.png" x="432" y="342" width="36" height="36" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="450" y="408">Battery</text>
            <text class="node-small" x="450" y="324">{_escape(battery)}</text>
            <text class="node-caption" x="450" y="422">{_escape(battery_v)}</text>
          </g>

          <g>
            <circle class="node{bypass_active if mode == 'bypass' else inverter_active}" cx="940" cy="224" r="34" />
            <image class="node-image{load_icon}" href="/assets/ups-icons/load.png" x="914" y="198" width="52" height="52" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="940" y="276">Load</text>
            <text class="node-small" x="940" y="298">{_escape(load)}</text>
            <text class="node-caption" x="940" y="318">{_escape(output_v)}</text>
          </g>
        </svg>

        <svg class="power mobile" viewBox="0 0 360 620" role="img" aria-label="UPS power flow diagram">
          <defs>
            <marker id="m-arrow-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path class="arrow" d="M0 0 L10 5 L0 10 Z" />
            </marker>
            <marker id="m-arrow-green" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path class="arrow bypass-active" d="M0 0 L10 5 L0 10 Z" />
            </marker>
            <marker id="m-arrow-muted" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path fill="#c8d1dd" d="M0 0 L10 5 L0 10 Z" />
            </marker>
          </defs>

          <path class="path{line_active}" marker-end="url(#{mobile_line_marker})" d="M180 72 V154" />
          <path class="path{line_active}" marker-end="url(#{mobile_line_marker})" d="M180 226 V306" />
          <path class="path{inverter_active}" marker-end="url(#{mobile_inverter_marker})" d="M180 378 V470" />
          <path class="path{battery_active}" marker-end="url(#{mobile_battery_marker})" d="M80 330 H142" />
          <path class="path{bypass_active}" marker-end="url(#{mobile_bypass_marker})" d="M180 92 H78 Q54 92 54 116 V500 Q54 524 78 524 H143" />

          <g>
            <circle class="node{input_node}" cx="180" cy="54" r="30" />
            <image class="node-image{input_icon}" href="/assets/ups-icons/input.png" x="158" y="32" width="44" height="44" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="245" y="50">Input</text>
            <text class="node-small" x="245" y="70">{_escape(input_v)}</text>
          </g>

          <g>
            <rect class="node{bypass_active}" x="32" y="166" width="48" height="48" rx="8" />
            <image class="node-image{' ' if mode == 'bypass' else ' muted'}" href="/assets/ups-icons/bypass.png" x="43" y="177" width="26" height="26" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="56" y="238">Bypass</text>
            <text class="node-caption" x="56" y="256">{'Active' if mode == 'bypass' else 'Standby'}</text>
          </g>

          <g>
            <rect class="node{avr_active}" x="142" y="154" width="76" height="72" rx="10" />
            <image class="node-image{avr_icon}" href="/assets/ups-icons/avr.png" x="157" y="174" width="46" height="38" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="252" y="188">AVR</text>
            <text class="node-caption" x="252" y="207">Line conditioner</text>
          </g>

          <g>
            <rect class="node{battery_active}" x="36" y="306" width="56" height="48" rx="8" />
            <image class="node-image{battery_icon}" href="/assets/ups-icons/battery.png" x="50" y="316" width="28" height="28" preserveAspectRatio="xMidYMid meet" />
            <text class="node-small" x="64" y="378">{_escape(battery)}</text>
            <text class="node-caption" x="64" y="396">{_escape(battery_v)}</text>
          </g>

          <g>
            <rect class="node{inverter_active}" x="142" y="306" width="76" height="72" rx="10" />
            <image class="node-image{inverter_icon}" href="/assets/ups-icons/inverter.png" x="157" y="323" width="46" height="42" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="252" y="346">Inverter</text>
          </g>

          <g>
            <circle class="node{bypass_active if mode == 'bypass' else inverter_active}" cx="180" cy="500" r="30" />
            <image class="node-image{load_icon}" href="/assets/ups-icons/load.png" x="158" y="478" width="44" height="44" preserveAspectRatio="xMidYMid meet" />
            <text class="node-text" x="252" y="492">Load</text>
            <text class="node-small" x="252" y="512">{_escape(load)}</text>
            <text class="node-caption" x="252" y="532">{_escape(output_v)}</text>
          </g>
        </svg>
      </div>
      <div class="legend"><span class="{active_path_class}">{_escape(mode_label)}</span><span class="bypass-leg">Bypass path</span><span class="inactive-leg">Inactive / standby path</span></div>
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
    icon = {
        "online": "avr",
        "runtime_minutes": "battery",
        "battery_charge_percent": "battery",
        "load_percent": "load",
        "battery_voltage": "battery",
        "input_voltage": "input",
        "output_voltage": "load",
    }.get(key, "avr")
    return f'<img src="/assets/ups-icons/{icon}.png" alt="">'


def _active(active: str, page: str) -> str:
    return "active" if active == page else ""


def _admin_active(active: str) -> str:
    return "active" if active in {"raw", "diagnostics", "settings", "logs", "updates"} else ""


def _format_time(value: datetime | None) -> str:
    if not value:
        return "-"
    return value.isoformat().replace("T", " ").replace("+00:00", " UTC")


def update_interval_label(value: str) -> str:
    return {"off": "off", "1d": "1 day", "7d": "7 days"}.get(value, value)


def render_settings_page(config: AppConfig) -> str:
    return page_shell(
        "Settings",
        "settings",
        f"""
        <section>
          <h1>Settings</h1>
          <p class="muted">Save writes config.yaml and restarts the service to apply backend, listener, SNMP, and MQTT runtime changes.</p>
          {render_config_form(config)}
          <div class="section-head" style="margin-top:18px;">
            <div>
              <h2>Home Assistant</h2>
              <p class="muted">Clear and republish retained MQTT discovery configs if the UPS was removed from Home Assistant.</p>
            </div>
            <button id="ha-rediscover" class="button secondary" type="button">Republish Discovery</button>
          </div>
          <p id="ha-rediscover-status" class="muted"></p>
          <script>
          (() => {{
            const button = document.getElementById("ha-rediscover");
            const status = document.getElementById("ha-rediscover-status");
            button.addEventListener("click", async () => {{
              if (!confirm("Republish Home Assistant MQTT discovery?\\n\\nThis clears retained discovery config topics and immediately publishes fresh configs for the UPS.")) return;
              button.disabled = true;
              status.textContent = "Republishing Home Assistant discovery...";
              try {{
                const response = await fetch("/homeassistant/rediscover", {{ method: "POST" }});
                const payload = await response.json();
                status.textContent = payload.message || (payload.ok ? "Discovery republished." : "Rediscovery failed.");
              }} catch (error) {{
                status.textContent = String(error);
              }} finally {{
                button.disabled = false;
              }}
            }});
          }})();
          </script>
        </section>
        """,
    )


def render_logs_page(config: AppConfig, lines: list[str], apcupsd_event_lines: list[str] | None = None) -> str:
    log_lines = "\n".join(_escape(line.rstrip("\n")) for line in lines)
    apcupsd_lines = "\n".join(_escape(line.rstrip("\n")) for line in (apcupsd_event_lines or []))
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
            <button id="refresh-logs" class="button secondary" type="button">Refresh</button>
          </div>
          <pre id="pug-log-view" class="log-view">{log_lines or 'No log lines available.'}</pre>
        </section>
        <section>
          <div class="section-head">
            <div>
              <h2>apcupsd Events</h2>
              <p class="muted">Showing the last {config.logging.web_tail_lines} lines from {_escape(config.logging.apcupsd_events_path)}.</p>
            </div>
          </div>
          <pre id="apcupsd-log-view" class="log-view">{apcupsd_lines or 'No apcupsd event lines available.'}</pre>
        </section>
        <script>
        (() => {{
          const setLines = (id, lines, emptyText) => {{
            const node = document.getElementById(id);
            if (node) node.textContent = lines && lines.length ? lines.join("\\n") : emptyText;
          }};
          const refresh = async () => {{
            const response = await fetch("/ui/live/logs", {{ cache: "no-store" }});
            if (!response.ok) return;
            const payload = await response.json();
            setLines("pug-log-view", payload.pug, "No log lines available.");
            setLines("apcupsd-log-view", payload.apcupsd, "No apcupsd event lines available.");
          }};
          document.getElementById("refresh-logs").addEventListener("click", refresh);
          setInterval(refresh, 5000);
        }})();
        </script>
        """,
    )


def render_updates_page(snapshot: UpdateSnapshot) -> str:
    output = "\n".join(_escape(line.rstrip("\n")) for line in snapshot.output)
    install_disabled = " disabled" if snapshot.status == "installing" or not snapshot.update_available else ""
    release_link = f'<a id="update-release-link" href="{_escape(snapshot.latest_release_url or "/updates")}">{_escape(snapshot.latest_release_url or "-")}</a>'
    return page_shell(
        "Updates",
        "updates",
        f"""
        <section>
          <div class="section-head">
            <div>
              <h1>Updates</h1>
              <p class="muted">Checks GitLab Releases from {_escape(snapshot.gitlab_base_url)} for {_escape(snapshot.project_path)}.</p>
            </div>
            <span id="update-status-pill" class="health {'warn' if snapshot.update_available else 'ok'}">{_escape(snapshot.status.title())}</span>
          </div>
          <div class="diagnostic-status">
            <dl class="detail-item"><dt>Installed Version</dt><dd id="update-installed">{_escape(snapshot.installed_version)}</dd></dl>
            <dl class="detail-item"><dt>Latest Version</dt><dd id="update-latest">{_escape(snapshot.latest_version or "-")}</dd></dl>
            <dl class="detail-item"><dt>Release Name</dt><dd id="update-release-name">{_escape(snapshot.latest_release_name or "-")}</dd></dl>
            <dl class="detail-item"><dt>Release Page</dt><dd>{release_link}</dd></dl>
            <dl class="detail-item"><dt>Check Interval</dt><dd id="update-interval">{_escape(update_interval_label(snapshot.check_interval))}</dd></dl>
            <dl class="detail-item"><dt>Last Check</dt><dd id="update-checked">{_escape(_format_time(snapshot.checked_at))}</dd></dl>
          </div>
          <p id="update-message" class="muted">{_escape(snapshot.error)}</p>
          <div class="actions">
            <button id="check-updates" type="button">Check for Update</button>
            <button id="install-update" class="danger" type="button"{install_disabled}>Download and Install</button>
          </div>
        </section>
        <section>
          <div class="section-head">
            <div>
              <h2>Update Progress</h2>
              <p class="muted">Update detection uses GitLab Releases. Install uses the local checkout, reinstalls PUG, then restarts the systemd service.</p>
            </div>
          </div>
          <pre id="update-output" class="log-view">{output or 'No update activity yet.'}</pre>
        </section>
        <script>
        (() => {{
          const fields = {{
            pill: document.getElementById("update-status-pill"),
            installed: document.getElementById("update-installed"),
            latest: document.getElementById("update-latest"),
            releaseName: document.getElementById("update-release-name"),
            releaseLink: document.getElementById("update-release-link"),
            interval: document.getElementById("update-interval"),
            checked: document.getElementById("update-checked"),
            message: document.getElementById("update-message"),
            output: document.getElementById("update-output"),
            install: document.getElementById("install-update"),
          }};
          const text = (value, fallback = "-") => value === null || value === undefined || value === "" ? fallback : String(value);
          const formatTime = (value) => text(value).replace("T", " ").replace("+00:00", " UTC");
          const intervalLabel = (value) => value === "off" ? "off" : value === "1d" ? "1 day" : "7 days";
          const update = (payload) => {{
            const installing = payload.status === "installing";
            fields.pill.textContent = text(payload.status, "idle").replace(/^./, c => c.toUpperCase());
            fields.pill.className = `health ${{payload.update_available ? "warn" : "ok"}}`;
            fields.installed.textContent = text(payload.installed_version);
            fields.latest.textContent = text(payload.latest_version);
            fields.releaseName.textContent = text(payload.latest_release_name);
            fields.releaseLink.textContent = text(payload.latest_release_url);
            if (payload.latest_release_url) fields.releaseLink.href = payload.latest_release_url;
            fields.interval.textContent = intervalLabel(payload.check_interval);
            fields.checked.textContent = formatTime(payload.checked_at);
            fields.message.textContent = text(payload.error, "");
            fields.output.textContent = payload.output && payload.output.length ? payload.output.join("\\n") : "No update activity yet.";
            fields.install.disabled = installing || !payload.update_available;
          }};
          const status = async () => {{
            const response = await fetch("/api/updates", {{ cache: "no-store" }});
            if (response.ok) update(await response.json());
          }};
          document.getElementById("check-updates").addEventListener("click", async () => {{
            const response = await fetch("/api/updates/check", {{ method: "POST" }});
            if (response.ok) update(await response.json());
          }});
          fields.install.addEventListener("click", async () => {{
            if (!confirm("Download and install the latest PUG update?\\n\\nThe service will restart after installation.")) return;
            const response = await fetch("/api/updates/install", {{ method: "POST" }});
            if (response.ok) {{
              const payload = await response.json();
              if (!payload.ok) alert(payload.message || "Update install could not start.");
              await status();
            }}
          }});
          setInterval(status, 3000);
        }})();
        </script>
        """,
    )


def diagnostic_summary(state: dict[str, Any], diagnostic: DiagnosticSnapshot) -> dict[str, str]:
    raw = state.get("raw", {})
    output = "\n".join(diagnostic.output)
    result = str(raw.get("SELFTEST", "") or "-")
    for line in reversed(diagnostic.output):
        if "Result of last self test:" in line:
            result = line.split("Result of last self test:", 1)[1].strip()
            break
    stage = "Idle"
    lowered = output.lower()
    if diagnostic.status == "running":
        if "restoring ups monitoring" in lowered:
            stage = "Restoring monitoring"
        elif "waiting for test to complete" in lowered:
            stage = "Waiting for test"
        elif "initiating self test" in lowered:
            stage = "Self-test running"
        elif "perform battery calibration" in lowered or diagnostic.action == "battery_calibration":
            stage = "Calibration running"
        else:
            stage = "Preparing"
    elif diagnostic.status in {"completed", "failed"}:
        stage = diagnostic.status.title()
    last_event = "-"
    for line in reversed(diagnostic.output):
        clean = line.strip()
        if clean and not clean[0].isdigit() and "select function" not in clean.lower():
            last_event = clean
            break
    return {
        "test_result": result,
        "stage": stage,
        "last_event": last_event,
        "last_transfer": str(raw.get("LASTXFER", "-")),
        "transfer_count": str(raw.get("NUMXFERS", "-")),
        "time_on_battery": str(raw.get("TONBATT", raw.get("CUMONBATT", "-"))),
        "last_on_battery": str(raw.get("XONBATT", "-")),
        "last_off_battery": str(raw.get("XOFFBATT", "-")),
    }


def render_diagnostic_summary_cards(summary: dict[str, str]) -> str:
    cards = [
        ("Test Result", "test_result"),
        ("Current Stage", "stage"),
        ("Latest Event", "last_event"),
        ("Last Transfer", "last_transfer"),
        ("Transfer Count", "transfer_count"),
        ("Time On Battery", "time_on_battery"),
        ("Last On Battery", "last_on_battery"),
        ("Last Off Battery", "last_off_battery"),
    ]
    return "".join(
        f'<dl class="detail-item"><dt>{_escape(label)}</dt><dd id="diag-summary-{key}">{_escape(summary.get(key, "-"))}</dd></dl>'
        for label, key in cards
    )


def render_diagnostics_page(state: dict[str, Any], config: AppConfig, diagnostic: DiagnosticSnapshot) -> str:
    output = "\n".join(_escape(line.rstrip("\n")) for line in diagnostic.output)
    action = diagnostic_label(diagnostic.action) if diagnostic.action else "-"
    started = display_value("last_update", diagnostic.started_at.isoformat() if diagnostic.started_at else "")
    finished = display_value("last_update", diagnostic.finished_at.isoformat() if diagnostic.finished_at else "")
    return_code = "-" if diagnostic.return_code is None else str(diagnostic.return_code)
    busy = diagnostic.status == "running"
    summary = diagnostic_summary(state, diagnostic)
    warning = (
        "This will temporarily stop apcupsd so apctest can own the UPS connection. "
        "Monitoring is unavailable while these diagnostics run. "
        "Until the diagnostic finishes, PUG cannot monitor live UPS status, and battery calibration may intentionally discharge the UPS for a long time."
    )
    return page_shell(
        "Diagnostics",
        "diagnostics",
        f"""
        <section>
          <div class="section-head">
            <div>
              <h1>Diagnostics</h1>
              <p class="muted">Live UPS state and apcupsd diagnostic actions.</p>
            </div>
            <span id="diagnostic-status-pill" class="health {'warn' if busy else 'ok'}">{_escape(diagnostic.status.title())}</span>
          </div>
          <p class="hint">{_escape(warning)}</p>
          <div class="diagnostic-status">
            <dl class="detail-item"><dt>UPS Status</dt><dd id="diag-ups-status">{_escape(display_value("status_text", state.get("status_text", "-")))}</dd></dl>
            <dl class="detail-item"><dt>Battery Charge</dt><dd id="diag-battery-charge">{_escape(display_value("battery_charge_percent", state.get("battery_charge_percent")))}</dd></dl>
            <dl class="detail-item"><dt>Runtime Remaining</dt><dd id="diag-runtime">{_escape(display_value("runtime_minutes", state.get("runtime_minutes")))}</dd></dl>
            <dl class="detail-item"><dt>Self Test Result</dt><dd id="diag-self-test">{_escape(str(state.get("raw", {}).get("SELFTEST", "-")))}</dd></dl>
          </div>
          <div class="actions">
            <button id="start-self-test" type="button" data-action="self_test"{' disabled' if busy else ''}>Start Self Test</button>
            <button id="start-calibration" class="danger" type="button" data-action="battery_calibration"{' disabled' if busy else ''}>Start Battery Calibration</button>
          </div>
        </section>
        <section>
          <div class="section-head">
            <div>
              <h2>Test Status</h2>
              <p class="muted">Updates live without reloading this page.</p>
            </div>
            <button id="refresh-diagnostics" class="button secondary" type="button">Refresh</button>
          </div>
          <div class="diagnostic-status">
            <dl class="detail-item"><dt>Action</dt><dd id="diag-action">{_escape(action)}</dd></dl>
            <dl class="detail-item"><dt>Started</dt><dd id="diag-started">{_escape(started)}</dd></dl>
            <dl class="detail-item"><dt>Finished</dt><dd id="diag-finished">{_escape(finished)}</dd></dl>
            <dl class="detail-item"><dt>Return Code</dt><dd id="diag-return-code">{_escape(return_code)}</dd></dl>
          </div>
          <div class="diagnostic-status" id="diag-summary-cards">
            {render_diagnostic_summary_cards(summary)}
          </div>
          <p id="diag-error" class="muted">{_escape(diagnostic.error)}</p>
          <div class="switch-row">
            <span class="muted">Raw apctest output is hidden by default.</span>
            <label class="switch"><input id="show-live-log" type="checkbox"><span class="slider"></span><span>Show live log</span></label>
          </div>
          <pre id="diag-output" class="log-view hidden">{output or 'No diagnostic output yet.'}</pre>
        </section>
        <script>
        (() => {{
          const warning = "{_escape(warning)}";
          const labels = {{ self_test: "self test", battery_calibration: "battery calibration" }};
          const fields = {{
            status: document.getElementById("diagnostic-status-pill"),
            upsStatus: document.getElementById("diag-ups-status"),
            battery: document.getElementById("diag-battery-charge"),
            runtime: document.getElementById("diag-runtime"),
            selfTest: document.getElementById("diag-self-test"),
            action: document.getElementById("diag-action"),
            started: document.getElementById("diag-started"),
            finished: document.getElementById("diag-finished"),
            returnCode: document.getElementById("diag-return-code"),
            error: document.getElementById("diag-error"),
            output: document.getElementById("diag-output"),
            logToggle: document.getElementById("show-live-log"),
          }};
          const summaryFields = {{
            test_result: document.getElementById("diag-summary-test_result"),
            stage: document.getElementById("diag-summary-stage"),
            last_event: document.getElementById("diag-summary-last_event"),
            last_transfer: document.getElementById("diag-summary-last_transfer"),
            transfer_count: document.getElementById("diag-summary-transfer_count"),
            time_on_battery: document.getElementById("diag-summary-time_on_battery"),
            last_on_battery: document.getElementById("diag-summary-last_on_battery"),
            last_off_battery: document.getElementById("diag-summary-last_off_battery"),
          }};
          const buttons = [
            document.getElementById("start-self-test"),
            document.getElementById("start-calibration"),
          ];
          const text = (value, fallback = "-") => {{
            if (value === null || value === undefined || value === "") return fallback;
            return String(value);
          }};
          const formatTime = (value) => text(value).replace("T", " ").replace("+00:00", " UTC");
          const setBusy = (busy) => buttons.forEach((button) => button.disabled = busy);
          const update = (payload) => {{
            const state = payload.state || {{}};
            const raw = state.raw || {{}};
            const diagnostic = payload.diagnostic || {{}};
            const summary = payload.summary || {{}};
            const busy = diagnostic.status === "running";
            fields.status.textContent = text(diagnostic.status, "idle").replace(/^./, c => c.toUpperCase());
            fields.status.className = `health ${{busy ? "warn" : "ok"}}`;
            fields.upsStatus.textContent = text(state.status_text);
            fields.battery.textContent = state.battery_charge_percent === undefined ? "-" : `${{state.battery_charge_percent}}%`;
            fields.runtime.textContent = state.runtime_minutes === undefined ? "-" : `${{state.runtime_minutes}} min`;
            fields.selfTest.textContent = text(raw.SELFTEST);
            fields.action.textContent = text(labels[diagnostic.action] || diagnostic.action);
            fields.started.textContent = formatTime(diagnostic.started_at);
            fields.finished.textContent = formatTime(diagnostic.finished_at);
            fields.returnCode.textContent = diagnostic.return_code === null || diagnostic.return_code === undefined ? "-" : diagnostic.return_code;
            fields.error.textContent = text(diagnostic.error, "");
            fields.output.textContent = diagnostic.output && diagnostic.output.length ? diagnostic.output.join("\\n") : "No diagnostic output yet.";
            Object.keys(summaryFields).forEach((key) => {{
              if (summaryFields[key]) summaryFields[key].textContent = text(summary[key]);
            }});
            setBusy(busy);
          }};
          const refresh = async () => {{
            const response = await fetch("/api/diagnostics", {{ cache: "no-store" }});
            if (response.ok) update(await response.json());
          }};
          const start = async (action) => {{
            const label = labels[action] || action;
            if (!confirm(`Start ${{label}}?\\n\\n${{warning}}`)) return;
            setBusy(true);
            const body = new URLSearchParams({{ action }});
            const response = await fetch("/api/diagnostics/start", {{
              method: "POST",
              headers: {{ "Content-Type": "application/x-www-form-urlencoded" }},
              body,
            }});
            const payload = await response.json();
            if (!payload.ok) alert(payload.message || "Unable to start diagnostic.");
            await refresh();
          }};
          buttons.forEach((button) => button.addEventListener("click", () => start(button.dataset.action)));
          document.getElementById("refresh-diagnostics").addEventListener("click", refresh);
          fields.logToggle.addEventListener("change", () => {{
            fields.output.classList.toggle("hidden", !fields.logToggle.checked);
          }});
          setInterval(refresh, 2000);
        }})();
        </script>
        """,
        auto_refresh=False,
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
      <label>apcupsd events path <input name="logging_apcupsd_events_path" value="{_escape(config.logging.apcupsd_events_path)}"></label>
      <label>Web log tail lines <input name="logging_web_tail_lines" type="number" min="1" value="{config.logging.web_tail_lines}"></label>
    </div>
  </fieldset>

  <fieldset>
    <legend>Updates</legend>
    <div class="grid">
      <label>GitLab base URL <input name="update_gitlab_base_url" value="{_escape(config.update.gitlab_base_url)}"></label>
      <label>GitLab project path <input name="update_project_path" value="{_escape(config.update.project_path)}"></label>
      <label>Release check interval
        <select name="update_check_interval">
          <option value="off"{_selected(config.update.check_interval, "off")}>off</option>
          <option value="1d"{_selected(config.update.check_interval, "1d")}>1 day</option>
          <option value="7d"{_selected(config.update.check_interval, "7d")}>7 days</option>
        </select>
      </label>
    </div>
  </fieldset>

  <fieldset>
    <legend>Diagnostics</legend>
    <p class="hint">The default preparation command stops apcupsd so apctest can access the UPS, and the restore command starts apcupsd again. Monitoring is unavailable while these diagnostics run.</p>
    <div class="grid">
      <label>Preparation command <input name="diagnostics_before_command" value="{_escape(format_command(config.diagnostics.before_command))}"></label>
      <label>Restore command <input name="diagnostics_after_command" value="{_escape(format_command(config.diagnostics.after_command))}"></label>
      <label>Self test command <input name="diagnostics_self_test_command" value="{_escape(format_command(config.diagnostics.self_test_command))}"></label>
      <label>Self test menu selection <input name="diagnostics_self_test_selection" value="{_escape(config.diagnostics.self_test_selection)}"></label>
      <label>Battery calibration command <input name="diagnostics_battery_calibration_command" value="{_escape(format_command(config.diagnostics.battery_calibration_command))}"></label>
      <label>Battery calibration menu selection <input name="diagnostics_battery_calibration_selection" value="{_escape(config.diagnostics.battery_calibration_selection)}"></label>
      <label>Command timeout seconds <input name="diagnostics_command_timeout_seconds" type="number" min="1" value="{config.diagnostics.command_timeout_seconds}"></label>
    </div>
  </fieldset>

  <button type="submit">Save Configuration</button>
</form>"""


def render_message_page(title: str, message: str, config: AppConfig, back_href: str = "/ui") -> str:
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
  <p><a href="{_escape(back_href)}">Back to Web UI</a></p>
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

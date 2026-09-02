from __future__ import annotations

import json
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from pug import __version__
from pug.config import NotificationConfig

LOGGER = logging.getLogger(__name__)
SEVERITIES = {"info": 0, "warning": 1, "critical": 2}


@dataclass(frozen=True)
class NotificationResult:
    provider: str
    ok: bool
    message: str = ""


class NotificationManager:
    def send(self, config: NotificationConfig, event: str, severity: str, message: str, details: dict[str, Any] | None = None) -> list[NotificationResult]:
        if SEVERITIES.get(severity, 0) < SEVERITIES.get(config.minimum_severity, 1):
            return []
        details = details or {}
        results: list[NotificationResult] = []
        if config.discord_enabled:
            results.append(self._discord(config, event, severity, message, details))
        if config.email_enabled:
            results.append(self._email(config, event, severity, message, details))
        for result in results:
            log = LOGGER.info if result.ok else LOGGER.error
            log("notification %s via %s: %s", event, result.provider, result.message)
        return results

    def _discord(self, config: NotificationConfig, event: str, severity: str, message: str, details: dict[str, Any]) -> NotificationResult:
        try:
            webhook = config.discord_webhook_url.strip() or _read_secret(config.discord_webhook_url_file)
            fields = [{"name": str(key).replace("_", " ").title(), "value": str(value)[:1024], "inline": True} for key, value in details.items()]
            payload = {
                "username": "PowerPi UPS Gateway",
                "allowed_mentions": {"parse": []},
                "embeds": [{"title": event.replace("_", " ").title(), "description": message, "color": {"info": 3447003, "warning": 16753920, "critical": 15158332}.get(severity, 3447003), "fields": fields[:25]}],
            }
            request = Request(
                webhook + ("&" if "?" in webhook else "?") + "wait=true",
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": f"PowerPi-UPS-Gateway/{__version__} (+https://git.vns.ae/ahsan/pug)",
                },
                method="POST",
            )
            with urlopen(request, timeout=config.timeout_seconds) as response:
                if response.status not in {200, 204}:
                    raise OSError(f"Discord returned HTTP {response.status}")
            return NotificationResult("discord", True, "delivered")
        except Exception as exc:
            return NotificationResult("discord", False, str(exc))

    def _email(self, config: NotificationConfig, event: str, severity: str, message: str, details: dict[str, Any]) -> NotificationResult:
        try:
            email = EmailMessage()
            email["Subject"] = f"[PUG {severity.upper()}] {event.replace('_', ' ').title()}"
            email["From"] = config.email_from
            email["To"] = ", ".join(config.email_recipients)
            lines = [message, "", *[f"{key.replace('_', ' ').title()}: {value}" for key, value in details.items()]]
            email.set_content("\n".join(lines))
            context = ssl.create_default_context()
            smtp_class = smtplib.SMTP_SSL if config.smtp_security == "tls" else smtplib.SMTP
            with smtp_class(config.smtp_host, config.smtp_port, timeout=config.timeout_seconds, context=context) if config.smtp_security == "tls" else smtp_class(config.smtp_host, config.smtp_port, timeout=config.timeout_seconds) as smtp:
                if config.smtp_security == "starttls":
                    smtp.starttls(context=context)
                if config.smtp_username:
                    smtp.login(config.smtp_username, _read_secret(config.smtp_password_file))
                smtp.send_message(email)
            return NotificationResult("email", True, "delivered")
        except Exception as exc:
            return NotificationResult("email", False, str(exc))


def _read_secret(path: str) -> str:
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"secret file is empty: {path}")
    return value

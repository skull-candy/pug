from pug.config import NotificationConfig
from pug.notifications import NotificationManager


def test_discord_uses_direct_webhook_without_reading_secret_file(monkeypatch) -> None:
    requests = []

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout):
        requests.append((request.full_url, timeout))
        return Response()

    monkeypatch.setattr("pug.notifications.urlopen", fake_urlopen)
    config = NotificationConfig(
        discord_enabled=True,
        discord_webhook_url="https://discord.com/api/webhooks/123/token",
        discord_webhook_url_file="/missing/file",
    )

    results = NotificationManager().send(config, "test_notification", "warning", "Test")

    assert results[0].ok is True
    assert requests == [("https://discord.com/api/webhooks/123/token?wait=true", 10)]

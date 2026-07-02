from __future__ import annotations

import argparse
import logging
import signal
import threading
import time

from pug.collector.apcupsd import ApcupsdCollector
from pug.collector.nut import NutCollector
from pug.collector.simulator import simulator_state
from pug.config import ConfigError, load_config
from pug.frontends.http import HttpFrontend
from pug.frontends.mqtt import MqttPublisher
from pug.logger import configure_logging
from pug.snmp.server import SnmpServer
from pug.state import StateStore

# Import modules for decorator registration.
from pug.snmp import apc_powernet as _apc_powernet  # noqa: F401
from pug.snmp import rfc1628 as _rfc1628  # noqa: F401

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PowerPi UPS Gateway")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--simulator", action="store_true", help="Use fake Smart-UPS 3000 state")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        parser.error(str(exc))
    configure_logging(config.logging.level, config.logging.file_path)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    initial = simulator_state() if args.simulator else None
    store = StateStore(initial)

    collector_thread = threading.Thread(
        target=_collector_loop,
        args=(store, config.backend, args.simulator, stop),
        name="collector",
        daemon=True,
    )
    collector_thread.start()
    worker_threads = [collector_thread]

    if config.http.enabled:
        http_thread = threading.Thread(
            target=HttpFrontend(store, args.config, config, config.http.listen, config.http.port).serve_forever,
            args=(stop,),
            name="http",
            daemon=True,
        )
        http_thread.start()
        worker_threads.append(http_thread)

    if config.mqtt.enabled:
        mqtt_thread = threading.Thread(
            target=MqttPublisher(store, config.mqtt).run_forever,
            args=(stop,),
            name="mqtt",
            daemon=True,
        )
        mqtt_thread.start()
        worker_threads.append(mqtt_thread)

    if config.snmp.enabled:
        server = SnmpServer(
            store,
            listen=config.snmp.listen,
            port=config.snmp.port,
            community=config.snmp.community,
            developer_log=config.snmp.developer_log,
        )
        server.serve_forever(stop)
    else:
        while not stop.is_set():
            time.sleep(1)

    for thread in worker_threads:
        thread.join(timeout=2)
    return 0


def _collector_loop(store: StateStore, backend_config, simulator: bool, stop: threading.Event) -> None:
    collector = None
    if not simulator:
        collector = NutCollector(backend_config.command) if backend_config.type == "nut" else ApcupsdCollector(backend_config.command)
    while not stop.is_set():
        try:
            state = simulator_state() if simulator else collector.collect()
            store.set(state)
            LOGGER.debug("updated UPS state from %s", state.source_backend)
        except Exception:
            LOGGER.exception("collector update failed")
        stop.wait(backend_config.poll_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(level: str = "INFO", file_path: str = "") -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if file_path:
        path = Path(file_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(path, encoding="utf-8"))
        except OSError:
            logging.getLogger(__name__).exception("failed to configure log file %s", file_path)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )

from __future__ import annotations

from abc import ABC, abstractmethod

from pug.state import UPSState


class Collector(ABC):
    @abstractmethod
    def collect(self) -> UPSState:
        """Return the latest UPS state from the backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FetchResponse:
    url: str
    ok: bool
    status_code: int | None = None
    text: str = ""
    error: str | None = None
    elapsed_ms: int | None = None


class Fetcher(ABC):
    """Transport abstraction. Swap implementations without touching parse/monitor."""

    async def astart(self) -> None:  # pragma: no cover - default no-op
        """Async initialization (e.g. launch a browser). Called once on worker startup."""
        return None

    @abstractmethod
    async def fetch(self, url: str) -> FetchResponse: ...

    async def aclose(self) -> None:  # pragma: no cover - default no-op
        return None

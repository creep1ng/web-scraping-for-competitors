from abc import ABC, abstractmethod
from typing import Optional


class BaseScraper(ABC):
    @abstractmethod
    async def fetch(self, url: str) -> Optional[str]:
        pass

    async def request(self, url: str, method: str = "GET", body: Optional[str] = None, headers: Optional[dict] = None) -> Optional[str]:
        """Generic HTTP request. Default fallback uses fetch (GET-only)."""
        if method.upper() == "GET":
            return await self.fetch(url)
        raise NotImplementedError(f"{self.__class__.__name__} does not support {method} requests")

    async def close(self) -> None:
        pass

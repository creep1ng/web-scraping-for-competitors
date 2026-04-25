from abc import ABC, abstractmethod
from typing import Optional


class BaseScraper(ABC):
    @abstractmethod
    async def fetch(self, url: str) -> Optional[str]:
        pass

    async def close(self) -> None:
        pass

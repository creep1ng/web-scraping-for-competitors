from typing import Optional
import aiohttp
from .base import BaseScraper


class CloudflareScraper(BaseScraper):
    def __init__(self, worker_url: str, api_token: str):
        self.worker_url = worker_url
        self.api_token = api_token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Authorization": f"Bearer {self.api_token}"}
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def fetch(self, url: str) -> Optional[str]:
        try:
            session = await self._get_session()
            async with session.post(
                self.worker_url,
                json={"url": url},
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("html", "")
                return None
        except Exception:
            return None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

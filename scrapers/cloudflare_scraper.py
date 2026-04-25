import aiohttp
import asyncio
from typing import Optional
from .base import BaseScraper


class CloudflareScraper(BaseScraper):
    def __init__(self, worker_url: str, api_token: str, max_retries: int = 3, timeout: int = 30):
        self.worker_url = worker_url.rstrip('/')
        self.api_token = api_token
        self.max_retries = max_retries
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_token}"}
            )
        return self._session

    async def fetch(self, url: str) -> Optional[str]:
        session = await self._get_session()
        payload = {"url": url}

        for attempt in range(self.max_retries):
            try:
                async with session.post(
                    self.worker_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("html")
                    elif response.status == 429:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return None
            except asyncio.TimeoutError:
                if attempt == self.max_retries - 1:
                    return None
                await asyncio.sleep(1)
            except Exception:
                if attempt == self.max_retries - 1:
                    return None
                await asyncio.sleep(1)

        return None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

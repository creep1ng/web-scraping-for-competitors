from typing import Optional
import aiohttp
from .base import BaseScraper
from logger import logger


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
        return await self.request(url, method="GET")

    async def request(self, url: str, method: str = "GET", body: Optional[str] = None, headers: Optional[dict] = None) -> Optional[str]:
        try:
            session = await self._get_session()
            payload = {"url": url, "method": method}
            if body is not None:
                payload["body"] = body
            if headers is not None:
                payload["headers"] = headers

            async with session.post(
                self.worker_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    html = data.get("html", "")
                    logger.debug(f"Request exitoso para {url}", extra={"url": url, "html": html})
                    return html
                else:
                    logger.warning(f"Respuesta no exitosa para {url}: status={response.status}", extra={"url": url})
                return None
        except Exception as e:
            logger.warning(f"Error en request para {url}: {e}", extra={"url": url}, exc_info=True)
            return None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

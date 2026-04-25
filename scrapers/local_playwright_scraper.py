import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext
from .base import BaseScraper


class LocalPlaywrightScraper(BaseScraper):
    def __init__(self, max_contexts: int = 5):
        self.max_contexts = max_contexts
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context_pool: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Browser:
        if self._browser is None or not self._browser.is_connected():
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            for _ in range(self.max_contexts):
                ctx = await self._browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                await self._context_pool.put(ctx)
        return self._browser

    async def fetch(self, url: str) -> Optional[str]:
        await self._ensure_browser()

        context = await self._context_pool.get()
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)
            html = await page.content()
            await page.close()
            return html
        except Exception:
            return None
        finally:
            if not self._context_pool.full():
                await self._context_pool.put(context)
            else:
                await context.close()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

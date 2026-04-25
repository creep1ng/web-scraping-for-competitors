import asyncio
from typing import List, Optional, Tuple
from playwright.async_api import async_playwright, Browser, BrowserContext
from .base import BaseScraper


class LocalPlaywrightScraper(BaseScraper):
    def __init__(self, max_contexts: int = 3):
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
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                await self._context_pool.put(ctx)
        return self._browser

    async def fetch(self, url: str) -> Optional[str]:
        await self._ensure_browser()
        context = await self._context_pool.get()
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)
            html = await page.content()
            await page.close()
            return html
        except Exception as e:
            print(f"Fetch error: {e}")
            return None
        finally:
            if not self._context_pool.full():
                await self._context_pool.put(context)
            else:
                await context.close()

    async def fetch_with_pagination_click(
        self,
        url: str,
        max_pages: int = 5,
        wait_time: float = 5.0,
        pagination_selector: str = "[data-pnumber]"
    ) -> List[Tuple[int, str]]:
        results = []
        await self._ensure_browser()
        context = await self._context_pool.get()

        try:
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(wait_time)

            html1 = await page.content()
            results.append((1, html1))

            for page_num in range(2, max_pages + 1):
                js_code = (
                    f"(function(){{"
                    f"var btn = jQuery(\"[data-pnumber='{page_num}']\");"
                    f"if(btn.length){{btn.trigger('click');}}"
                    f"}})()"
                )
                await page.evaluate(js_code)
                await page.wait_for_timeout(wait_time)

                html = await page.content()
                results.append((page_num, html))

            return results

        except Exception as e:
            print(f"  [fetch_with_pagination] Error: {e}")
            return results if results else []
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

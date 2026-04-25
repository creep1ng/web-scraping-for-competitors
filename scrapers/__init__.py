from os import getenv
from .base import BaseScraper
from .cloudflare_scraper import CloudflareScraper
from .local_playwright_scraper import LocalPlaywrightScraper


def get_scraper() -> BaseScraper:
    engine = getenv("SCRAPER_ENGINE", "local")

    if engine == "cloudflare":
        return CloudflareScraper(
            worker_url=getenv("CLOUDFLARE_WORKER_URL", ""),
            api_token=getenv("CLOUDFLARE_API_TOKEN", "")
        )
    else:
        return LocalPlaywrightScraper()


__all__ = ["BaseScraper", "CloudflareScraper", "LocalPlaywrightScraper", "get_scraper"]

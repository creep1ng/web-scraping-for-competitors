import asyncio
import os
from dotenv import load_dotenv
import pandas as pd
from typing import List, Dict

from scrapers import get_scraper
from extractors import get_strategy_for_url
from extractors.strategies import EmergenteStrategy
from logger import logger

load_dotenv()


async def process_single_url(url: str, scraper, semaphore: asyncio.Semaphore, max_pages: int = 1) -> List[Dict]:
    """Process a single URL (first page + pagination). Returns products."""
    async with semaphore:
        url = url.strip()
        if not url:
            return []

        logger.info(f"Procesando: {url}", extra={"url": url})

        html = await scraper.fetch(url)
        if not html:
            logger.error(f"No se pudo obtener HTML de {url}", extra={"url": url})
            return []

        strategy = get_strategy_for_url(url)
        all_products = strategy.extract_products(html, url)
        logger.info(f"Pagina 1: {len(all_products)} productos", extra={"url": url})

        # URL-based pagination
        if strategy.has_pagination(html, url) and max_pages > 1:
            total_pages = min(strategy.get_total_pages(html, url), max_pages)
            page_urls = strategy.get_pagination_urls(url, total_pages)
            logger.info(f"Navegando {len(page_urls)} paginas adicionales por URL", extra={"url": url})

            for page_url in page_urls:
                page_html = await scraper.fetch(page_url)
                if page_html:
                    page_products = strategy.extract_products(page_html, page_url)
                    if page_products:
                        all_products.extend(page_products)
                await asyncio.sleep(0.3)

        # AJAX pagination (only if scraper supports clicks)
        elif strategy.is_ajax_pagination(html, url) and max_pages > 1:
            if hasattr(scraper, 'fetch_with_pagination_click'):
                pages_to_scrape = min(strategy.get_total_pages(html, url), max_pages)
                logger.info(f"Paginacion AJAX: {pages_to_scrape} paginas con clicks", extra={"url": url})
                try:
                    page_contents = await scraper.fetch_with_pagination_click(
                        url,
                        max_pages=pages_to_scrape,
                        wait_time=5.0,
                        pagination_selector="[data-pnumber]"
                    )
                    for page_num, page_html in page_contents[1:]:
                        page_products = strategy.extract_products(page_html, url)
                        all_products.extend(page_products)
                        logger.debug(f"Pagina {page_num} scrapeada: {len(page_products)} productos", extra={"url": url})
                except Exception as e:
                    logger.warning(f"Error durante paginacion AJAX: {e}", extra={"url": url}, exc_info=True)
            else:
                logger.warning(
                    f"Paginacion AJAX detectada pero scraper no soporta clicks. "
                    f"Solo se extrae la primera página.",
                    extra={"url": url}
                )

        logger.info(f"Total productos para {url}: {len(all_products)}", extra={"url": url})
        return all_products


async def discover_urls(url: str, scraper, semaphore: asyncio.Semaphore) -> List[str]:
    """Discover additional URLs from a landing page."""
    async with semaphore:
        html = await scraper.fetch(url)
        if not html:
            return []

        strategy = get_strategy_for_url(url)
        discovered = strategy.discover_urls(html, url)

        # Special handling for Emergente sitemap
        if isinstance(strategy, EmergenteStrategy):
            sitemap_urls = [u for u in discovered if u.endswith('.xml')]
            other_urls = [u for u in discovered if not u.endswith('.xml')]
            product_urls = []
            for sitemap_url in sitemap_urls:
                xml_html = await scraper.fetch(sitemap_url)
                if xml_html:
                    parsed = strategy.parse_sitemap(xml_html, url)
                    product_urls.extend(parsed)
            if product_urls:
                # Cap emergente sitemap products to avoid overwhelming the worker
                max_sitemap_products = int(os.getenv("MAX_SITEMAP_PRODUCTS", "300"))
                if len(product_urls) > max_sitemap_products:
                    logger.info(f"Limitando productos Emergente de {len(product_urls)} a {max_sitemap_products}")
                    product_urls = product_urls[:max_sitemap_products]
            return product_urls + other_urls

        return discovered


async def main():
    urls_file = "urls.txt"
    if not os.path.exists(urls_file):
        logger.error(f"No se encontro {urls_file}")
        return

    with open(urls_file, "r") as f:
        initial_urls = [line.strip() for line in f if line.strip()]

    if not initial_urls:
        logger.warning("No hay URLs para procesar")
        return

    max_concurrency = int(os.getenv("MAX_CONCURRENCY", "3"))
    max_pages_per_url = int(os.getenv("MAX_PAGES_PER_URL", "5"))
    semaphore = asyncio.Semaphore(max_concurrency)

    scraper = get_scraper()

    try:
        all_products: List[Dict] = []
        processed_urls: set = set()
        urls_to_process: List[str] = []

        # Phase 1: discover additional URLs from initial URLs
        for url in initial_urls:
            if url in processed_urls:
                continue
            processed_urls.add(url)
            urls_to_process.append(url)

            new_urls = await discover_urls(url, scraper, semaphore)
            for new_url in new_urls:
                if new_url not in processed_urls:
                    processed_urls.add(new_url)
                    urls_to_process.append(new_url)

        logger.info(f"Iniciando scraping de {len(urls_to_process)} URLs...")
        logger.info(f"Concurrency: {max_concurrency}, Max pages/URL: {max_pages_per_url}")

        # Phase 2: process all URLs with pagination
        # Process in batches to control concurrency and memory
        batch_size = max_concurrency * 4
        for i in range(0, len(urls_to_process), batch_size):
            batch = urls_to_process[i:i+batch_size]
            tasks = [process_single_url(url, scraper, semaphore, max_pages_per_url) for url in batch]
            results = await asyncio.gather(*tasks)
            for result in results:
                if result:
                    all_products.extend(result)
            logger.info(
                f"Batch completado: {min(i+batch_size, len(urls_to_process))}/{len(urls_to_process)} URLs procesadas, "
                f"{len(all_products)} productos acumulados"
            )

        if all_products:
            df = pd.DataFrame(all_products)
            original_count = len(df)
            df = df.drop_duplicates(subset=["link"])
            dedup_count = len(df)
            if original_count != dedup_count:
                logger.info(f"Deduplicacion: {original_count} -> {dedup_count} productos unicos")

            df.to_csv("resultados_competidores.csv", index=False)
            df.to_excel("resultados_competidores.xlsx", index=False)

            logger.info(f"COMPLETADO: {dedup_count} productos unicos extraidos")
            logger.info(f"CSV: resultados_competidores.csv, Excel: resultados_competidores.xlsx")
            logger.debug(f"Datos del DataFrame", extra={"html": df.head(5).to_dict()})
        else:
            logger.warning("No se encontraron productos")

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())

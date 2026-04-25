import asyncio
import os
from dotenv import load_dotenv
import pandas as pd
from typing import List, Dict

from scrapers import get_scraper
from extractors import extract_products_from_html, get_pagination_info
from logger import logger

load_dotenv()


async def process_url(url: str, scraper, semaphore: asyncio.Semaphore, max_pages: int = 1) -> List[Dict]:
    async with semaphore:
        url = url.strip()
        if not url:
            return []

        logger.info(f"Procesando: {url}", extra={"url": url})
        logger.debug(f"Iniciando procesamiento de URL", extra={"url": url})

        html = await scraper.fetch(url)
        if not html:
            logger.error(f"No se pudo obtener HTML de {url}", extra={"url": url})
            return []

        logger.debug(f"HTML obtenido para {url}", extra={"url": url, "html": html})

        pagination = get_pagination_info(html)
        all_products = extract_products_from_html(html, url)
        logger.info(f"Pagina 1: {len(all_products)} productos", extra={"url": url})

        if pagination["has_pagination"] and pagination["ajax_pagination"]:
            pages_to_scrape = min(pagination["total_pages"], max_pages)
            logger.info(f"Paginacion AJAX: {pagination['total_pages']} paginas totales", extra={"url": url})
            logger.debug(f"Navegando {pages_to_scrape} paginas con clicks", extra={"url": url})

            try:
                page_contents = await scraper.fetch_with_pagination_click(
                    url,
                    max_pages=pages_to_scrape,
                    wait_time=5.0,
                    pagination_selector="[data-pnumber]"
                )

                for page_num, page_html in page_contents[1:]:
                    page_products = extract_products_from_html(page_html, url)
                    all_products.extend(page_products)
                    logger.debug(f"Pagina {page_num} scrapeada: {len(page_products)} productos", extra={"url": url, "html": page_html})

            except Exception as e:
                logger.warning(f"Error durante paginacion: {e}", extra={"url": url}, exc_info=True)

        elif pagination["has_pagination"] and max_pages > 1:
            logger.info(f"Navegando {max_pages - 1} paginas por URL", extra={"url": url})
            for page_num in range(2, max_pages + 1):
                page_url = f"{url.rstrip('/')}/page/{page_num}/"
                page_html = await scraper.fetch(page_url)
                if page_html:
                    page_products = extract_products_from_html(page_html, page_url)
                    if page_products:
                        all_products.extend(page_products)
                await asyncio.sleep(0.3)

        logger.info(f"Total productos: {len(all_products)}", extra={"url": url})
        return all_products


async def main():
    urls_file = "urls.txt"
    if not os.path.exists(urls_file):
        logger.error(f"No se encontro {urls_file}")
        return

    with open(urls_file, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        logger.warning("No hay URLs para procesar")
        return

    max_concurrency = int(os.getenv("MAX_CONCURRENCY", "3"))
    max_pages_per_url = int(os.getenv("MAX_PAGES_PER_URL", "5"))
    semaphore = asyncio.Semaphore(max_concurrency)

    logger.info(f"Iniciando scraping de {len(urls)} URLs...")
    logger.info(f"Concurrency: {max_concurrency}, Max pages/URL: {max_pages_per_url}")

    scraper = get_scraper()

    try:
        tasks = [process_url(url, scraper, semaphore, max_pages_per_url) for url in urls]
        results = await asyncio.gather(*tasks)

        all_products = []
        for result in results:
            if result:
                all_products.extend(result)

        if all_products:
            df = pd.DataFrame(all_products)
            df.to_csv("resultados_competidores.csv", index=False)
            df.to_excel("resultados_competidores.xlsx", index=False)

            logger.info(f"COMPLETADO: {len(all_products)} productos extraidos")
            logger.info(f"CSV: resultados_competidores.csv, Excel: resultados_competidores.xlsx")

            logger.debug(f"Datos del DataFrame", extra={"html": df.head(5).to_dict()})
        else:
            logger.warning("No se encontraron productos")

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
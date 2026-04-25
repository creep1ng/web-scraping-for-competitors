import asyncio
import os
from dotenv import load_dotenv
import pandas as pd
from typing import List, Dict

from scrapers import get_scraper
from extractors import extract_products_from_html, get_pagination_info

load_dotenv()


async def process_url(url: str, scraper, semaphore: asyncio.Semaphore, max_pages: int = 1) -> List[Dict]:
    async with semaphore:
        url = url.strip()
        if not url:
            return []

        print(f"\n{'='*60}")
        print(f"Procesando: {url}")

        html = await scraper.fetch(url)
        if not html:
            print(f"  Error: No se pudo obtener HTML de {url}")
            return []

        pagination = get_pagination_info(html)
        all_products = extract_products_from_html(html, url)
        print(f"  Página 1: {len(all_products)} productos")

        if pagination["has_pagination"] and pagination["ajax_pagination"]:
            pages_to_scrape = min(pagination["total_pages"], max_pages)
            print(f"  Paginación AJAX: {pagination['total_pages']} páginas totales")
            print(f"  Navegando {pages_to_scrape} páginas con clicks...")

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

            except Exception as e:
                print(f"  Error durante paginación: {e}")

        elif pagination["has_pagination"] and max_pages > 1:
            print(f"  Navegando {max_pages - 1} páginas por URL...")
            for page_num in range(2, max_pages + 1):
                page_url = f"{url.rstrip('/')}/page/{page_num}/"
                page_html = await scraper.fetch(page_url)
                if page_html:
                    page_products = extract_products_from_html(page_html, page_url)
                    if page_products:
                        all_products.extend(page_products)
                await asyncio.sleep(0.3)

        print(f"  Total productos: {len(all_products)}")
        return all_products


async def main():
    urls_file = "urls.txt"
    if not os.path.exists(urls_file):
        print(f"Error: No se encontró {urls_file}")
        return

    with open(urls_file, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("No hay URLs para procesar")
        return

    max_concurrency = int(os.getenv("MAX_CONCURRENCY", "3"))
    max_pages_per_url = int(os.getenv("MAX_PAGES_PER_URL", "5"))
    semaphore = asyncio.Semaphore(max_concurrency)

    print(f"Iniciando scraping de {len(urls)} URLs...")
    print(f"Concurrency: {max_concurrency}, Max pages/URL: {max_pages_per_url}")

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

            print(f"\n{'='*60}")
            print(f"COMPLETADO:")
            print(f"  Total productos: {len(all_products)}")
            print(f"  CSV: resultados_competidores.csv")
            print(f"  Excel: resultados_competidores.xlsx")

            print(f"\n  Vista previa:")
            for i, row in df.head(5).iterrows():
                print(f"    {i+1}. {row['nombre_producto'][:50]} - {row['precio']}")
        else:
            print("\nNo se encontraron productos.")

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())

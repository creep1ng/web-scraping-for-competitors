import asyncio
import os
from dotenv import load_dotenv
import pandas as pd

from scrapers import get_scraper
from extractor import extract_product_info_async

load_dotenv()


async def process_url(url: str, scraper, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        url = url.strip()
        if not url:
            return None

        print(f"Procesando: {url}")

        html = await scraper.fetch(url)
        if not html:
            print(f"  Error al obtener HTML: {url}")
            return {"nombre_pagina": "error", "link": url, "nombre_producto": "", "precio": ""}

        try:
            result = await extract_product_info_async(html, url)
            print(f"  OK: {result.get('nombre_producto', 'N/A')}")
            return result
        except Exception as e:
            print(f"  Error al extraer: {e}")
            return {"nombre_pagina": "error", "link": url, "nombre_producto": "", "precio": ""}


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

    print(f"Procesando {len(urls)} URLs...")

    max_concurrency = int(os.getenv("MAX_CONCURRENCY", "10"))
    semaphore = asyncio.Semaphore(max_concurrency)

    scraper = get_scraper()

    try:
        tasks = [process_url(url, scraper, semaphore) for url in urls]
        results = await asyncio.gather(*tasks)

        valid_results = [r for r in results if r is not None]

        df = pd.DataFrame(valid_results)
        df.to_csv("resultados_competidores.csv", index=False)
        df.to_excel("resultados_competidores.xlsx", index=False)

        print(f"\nCompletado. {len(valid_results)} productos exportados.")
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())

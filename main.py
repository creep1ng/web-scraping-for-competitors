#!/usr/bin/env python3
"""
Web Scraping para Competidores - Sistema de caché por stages

Stages:
  1. scrape  - Extrae productos de páginas de competidores y los guarda en caché
  2. compare - Ejecuta fuzzy matching usando datos cacheados o CSV directo

Uso:
    python main.py scrape                    # scrape con caché habilitado por defecto
    python main.py scrape --no-cache        # forzar re-scrape de todo
    python main.py scrape --refresh-emergente  # re-scrape solo Emergente
    python main.py compare                  # compare usando datos en caché
    python main.py compare --own X.csv      # compare con archivo propio custom
    python main.py compare --competitors Y.csv  # compare con CSV de competidores directo
"""
import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
from typing import List, Dict, Optional

from scrapers import get_scraper
from extractors import get_strategy_for_url
from extractors.strategies import EmergenteStrategy
from logger import logger

load_dotenv()

CACHE_DIR = Path("cache/scraping")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_path(page_name: str) -> Path:
    safe_name = page_name.replace(".", "_").replace("/", "_")
    return CACHE_DIR / safe_name


def load_cache_meta(page_name: str) -> dict:
    meta_path = get_cache_path(page_name) / "meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            return json.load(f)
    return {}


def save_cache_meta(page_name: str, meta: dict):
    cache_path = get_cache_path(page_name)
    cache_path.mkdir(parents=True, exist_ok=True)
    meta_path = cache_path / "meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


def save_page_cache(page_name: str, products: List[Dict]):
    cache_path = get_cache_path(page_name)
    cache_path.mkdir(parents=True, exist_ok=True)

    if products:
        df = pd.DataFrame(products)
        df.to_csv(cache_path / "products.csv", index=False)

    meta = {
        "page_name": page_name,
        "product_count": len(products),
        "cached_at": datetime.now().isoformat(),
    }
    save_cache_meta(page_name, meta)
    logger.info(f"Cache guardado: {page_name} ({len(products)} productos)")


def load_page_cache(page_name: str) -> Optional[List[Dict]]:
    cache_path = get_cache_path(page_name)
    products_file = cache_path / "products.csv"

    if products_file.exists():
        df = pd.read_csv(products_file)
        logger.info(f"Cache cargado: {page_name} ({len(df)} productos)")
        return df.to_dict("records")
    return None


def get_cached_pages() -> List[str]:
    if not CACHE_DIR.exists():
        return []
    pages = []
    for item in CACHE_DIR.iterdir():
        if item.is_dir() and (item / "products.csv").exists():
            meta = load_cache_meta(item.name)
            pages.append(meta.get("page_name", item.name))
    return pages


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
                max_sitemap_products = int(os.getenv("MAX_SITEMAP_PRODUCTS", "300"))
                if len(product_urls) > max_sitemap_products:
                    logger.info(f"Limitando productos Emergente de {len(product_urls)} a {max_sitemap_products}")
                    product_urls = product_urls[:max_sitemap_products]
            return product_urls + other_urls

        return discovered


async def run_scraping(args: argparse.Namespace):
    """Execute the scraping stage with caching support."""
    urls_file = "urls.txt"
    if not os.path.exists(urls_file):
        logger.error(f"No se encontro {urls_file}")
        return 1

    with open(urls_file, "r") as f:
        initial_urls = [line.strip() for line in f if line.strip()]

    if not initial_urls:
        logger.warning("No hay URLs para procesar")
        return 1

    max_concurrency = int(os.getenv("MAX_CONCURRENCY", "3"))
    max_pages_per_url = int(os.getenv("MAX_PAGES_PER_URL", "5"))
    semaphore = asyncio.Semaphore(max_concurrency)

    scraper = get_scraper()

    pages_to_scrape = []
    if args.refresh:
        pages_to_scrape = args.refresh
        logger.info(f"Refrescando páginas específicas: {pages_to_scrape}")

    try:
        all_products: List[Dict] = []
        processed_urls: set = set()
        urls_to_process: List[str] = []

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

            grouped = df.groupby("nombre_pagina")
            for page_name, page_df in grouped:
                if pages_to_scrape and page_name not in pages_to_scrape:
                    continue
                save_page_cache(page_name, page_df.to_dict("records"))

            logger.info(f"COMPLETADO: {dedup_count} productos unicos extraidos")
            logger.info(f"CSV: resultados_competidores.csv, Excel: resultados_competidores.xlsx")

            cached_pages = get_cached_pages()
            logger.info(f"Páginas en caché: {len(cached_pages)}")
            for p in cached_pages:
                logger.info(f"  - {p}")
        else:
            logger.warning("No se encontraron productos")

        return 0

    finally:
        await scraper.close()


def run_compare(args: argparse.Namespace):
    """Execute the fuzzy matching comparison stage."""
    from comparador import (
        load_own_products, load_competitor_products,
        generate_report, DEFAULT_THRESHOLD
    )

    if args.use_cache:
        comp_path = Path("resultados_competidores.csv")
        if not comp_path.exists():
            cached_products = []
            for cache_dir in CACHE_DIR.iterdir():
                if cache_dir.is_dir():
                    products_file = cache_dir / "products.csv"
                    if products_file.exists():
                        df = pd.read_csv(products_file)
                        cached_products.append(df)

            if cached_products:
                comp_df = pd.concat(cached_products, ignore_index=True)
                comp_path = Path("resultados_competidores.csv")
                comp_df.to_csv(comp_path, index=False)
                logger.info(f"Datos cacheados combinados: {len(comp_df)} productos")
            else:
                logger.error("No hay datos en caché y resultados_competidores.csv no existe")
                return 1

    own_path = args.own or Path("/home/creep/Downloads/wc-product-export-25-4-2026-1777140983496.csv")
    comp_path = args.competitors or Path("resultados_competidores.csv")
    threshold = args.threshold or DEFAULT_THRESHOLD

    if not own_path.exists():
        print(f"Error: archivo propio no encontrado: {own_path}")
        return 1
    if not comp_path.exists():
        print(f"Error: archivo de competidores no encontrado: {comp_path}")
        return 1

    print("Cargando productos propios...")
    own_df = load_own_products(own_path)
    print(f"  {len(own_df)} productos cargados desde {own_path.name}")

    print("Cargando productos de competidores...")
    comp_df = load_competitor_products(comp_path)
    print(f"  {len(comp_df)} productos cargados desde {comp_path.name}")
    for page in comp_df["nombre_pagina"].unique():
        count = len(comp_df[comp_df["nombre_pagina"] == page])
        print(f"    - {page}: {count}")

    print(f"\nGenerando reporte comparativo (umbral: {threshold})...")
    report = generate_report(own_df, comp_df, threshold)

    output_dir = args.output_dir or Path(".")
    output_xlsx = output_dir / "reporte_comparativo_precios.xlsx"
    output_csv = output_dir / "reporte_comparativo_precios.csv"

    from comparador import generate_multi_sheet_report
    generate_multi_sheet_report(report, output_xlsx)
    print(f"  Guardado: {output_xlsx}")

    report.to_csv(output_csv, index=False)
    print(f"  Guardado: {output_csv}")

    low_confidence = report[
        (report["score_emergente_com_co"] < threshold) &
        (report["score_ingesolar_com_co"] < threshold) &
        (report["score_ineldec_com"] < threshold)
    ]
    if not low_confidence.empty:
        output_revisar = output_dir / "matches_revisar.xlsx"
        low_confidence.to_excel(output_revisar, index=False)
        print(f"  Guardado: {output_revisar} ({len(low_confidence)} productos sin match)")

    stats = {
        "total_productos": len(report),
        "matches_emergente": (report["score_emergente_com_co"] >= threshold).sum(),
        "matches_ingesolar": (report["score_ingesolar_com_co"] >= threshold).sum(),
        "matches_ineldec": (report["score_ineldec_com"] >= threshold).sum(),
    }
    print("\nEstadísticas:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Web Scraping para Competidores - Sistema de caché por stages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py scrape                    # scrape con caché habilitado
  python main.py scrape --no-cache         # forzar re-scrape total
  python main.py scrape --refresh emergente.com.co  # re-scrape página específica
  python main.py compare                   # compare usando datos en caché
  python main.py compare --own X.csv      # compare con archivo propio custom
  python main.py compare --use-cache       # fuerza uso de datos cacheados
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    scrape_parser = subparsers.add_parser("scrape", help="Ejecutar scraping de competidores")
    scrape_parser.add_argument("--no-cache", action="store_true",
                              help="Ignorar caché existente y hacer scrape completo")
    scrape_parser.add_argument("--refresh", nargs="+", metavar="PAGE",
                              help="Re-scrape páginas específicas (ej: emergente.com.co)")

    compare_parser = subparsers.add_parser("compare", help="Ejecutar fuzzy matching")
    compare_parser.add_argument("--own", type=Path,
                               help="Ruta al CSV de productos propios")
    compare_parser.add_argument("--competitors", type=Path,
                               help="Ruta al CSV de competidores (overrides --use-cache)")
    compare_parser.add_argument("--use-cache", action="store_true",
                               help="Usar datos cacheados para competidores")
    compare_parser.add_argument("--threshold", type=int,
                               help=f"Umbral de similitud (default: {75})")
    compare_parser.add_argument("--output-dir", type=Path,
                               help="Directorio para archivos de salida")

    list_parser = subparsers.add_parser("list-cache", help="Listar páginas en caché")

    clean_parser = subparsers.add_parser("clean-cache", help="Limpiar caché")
    clean_parser.add_argument("--all", action="store_true", help="Limpiar todo el caché")
    clean_parser.add_argument("pages", nargs="*", help="Páginas específicas a limpiar")

    args = parser.parse_args()

    if args.command == "scrape":
        return asyncio.run(run_scraping(args))
    elif args.command == "compare":
        return run_compare(args)
    elif args.command == "list-cache":
        pages = get_cached_pages()
        if pages:
            print("Páginas en caché:")
            for page in pages:
                meta = load_cache_meta(page)
                cached_at = meta.get("cached_at", "desconocida")
                count = meta.get("product_count", 0)
                print(f"  - {page}: {count} productos (cached: {cached_at})")
        else:
            print("No hay páginas en caché")
        return 0
    elif args.command == "clean-cache":
        if args.all:
            import shutil
            if CACHE_DIR.exists():
                shutil.rmtree(CACHE_DIR)
                CACHE_DIR.mkdir(parents=True)
            print("Caché limpiado completamente")
        elif args.pages:
            for page in args.pages:
                cache_path = get_cache_path(page)
                if cache_path.exists():
                    import shutil
                    shutil.rmtree(cache_path)
                    print(f"Caché de {page} eliminado")
                else:
                    print(f"Caché de {page} no encontrado")
        else:
            print("Use --all para limpiar todo o especifique páginas")
        return 0
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    exit(main())

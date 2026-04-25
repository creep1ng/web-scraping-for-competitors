from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from logger import logger


def parse_price(text: str) -> Optional[str]:
    text = text.strip()
    match = re.search(r'\$?\s*([\d.,]+)', text)
    if match:
        return match.group(1).replace(',', '.')
    return None


def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _extract_domain(url: str) -> str:
    match = re.search(r'(?:https?://)?(?:www\.)?([^/]+)', url)
    return match.group(1) if match else url


# =============================================================================
# Default selectors used by most WooCommerce sites
# =============================================================================
DEFAULT_PRODUCT_SELECTORS = [
    "li.product",
    "li.type-product",
    ".products .product",
    ".wc-block-grid__product",
    ".eael-product-wrap",
]

DEFAULT_TITLE_SELECTORS = [
    "h2.woocommerce-loop-product__title",
    "h2.product-title",
    ".woocommerce-LoopProduct-link h2",
    ".product-details-wrap h2",
]

DEFAULT_PRICE_SELECTORS = [
    ".woocommerce-Price-amount",
    ".price .amount",
    ".eael-product-price",
    "span.woocommerce-Price-amount",
]

DEFAULT_LINK_SELECTORS = [
    "a.woocommerce-LoopProduct-link",
    "a.product-link",
    ".woocommerce-LoopProduct-link",
]


def _extract_product_data(element, base_url: str,
                         title_selectors=DEFAULT_TITLE_SELECTORS,
                         price_selectors=DEFAULT_PRICE_SELECTORS,
                         link_selectors=DEFAULT_LINK_SELECTORS) -> Optional[Dict[str, str]]:
    title = None
    link = None
    price = None

    for selector in title_selectors:
        title_elem = element.select_one(selector)
        if title_elem:
            title = clean_text(title_elem.get_text())
            break

    if not title:
        h2 = element.find("h2")
        if h2:
            title = clean_text(h2.get_text())
        else:
            h3 = element.find("h3")
            if h3:
                title = clean_text(h3.get_text())

    if not title or len(title) < 3:
        return None

    for selector in link_selectors:
        link_elem = element.select_one(selector)
        if link_elem and link_elem.get("href"):
            link = link_elem.get("href")
            break

    if not link:
        anchor = element.find("a", href=True)
        if anchor:
            link = anchor.get("href")

    for selector in price_selectors:
        price_elem = element.select_one(selector)
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            if price_text:
                parsed = parse_price(price_text)
                if parsed:
                    price = f"$ {parsed}"
                    break

    if not price:
        price_texts = element.find_all(string=lambda t: t and "$" in str(t))
        for pt in price_texts:
            parsed = parse_price(pt)
            if parsed:
                price = f"$ {parsed}"
                break

    ins = element.select_one("ins")
    if ins:
        ins_text = ins.get_text(strip=True)
        if ins_text:
            parsed = parse_price(ins_text)
            if parsed:
                price = f"$ {parsed}"

    if not link:
        link = base_url

    return {
        "nombre_pagina": _extract_domain(base_url),
        "link": link or "",
        "nombre_producto": title or "",
        "precio": price or "",
    }


def _generic_extract(html: str, url: str,
                    product_selectors=DEFAULT_PRODUCT_SELECTORS,
                    title_selectors=DEFAULT_TITLE_SELECTORS,
                    price_selectors=DEFAULT_PRICE_SELECTORS,
                    link_selectors=DEFAULT_LINK_SELECTORS) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    products = []
    seen_titles = set()
    selector_used = None

    for product_sel in product_selectors:
        product_elems = soup.select(product_sel)
        if product_elems:
            for product_elem in product_elems:
                product_data = _extract_product_data(
                    product_elem, url,
                    title_selectors=title_selectors,
                    price_selectors=price_selectors,
                    link_selectors=link_selectors
                )
                if product_data and product_data["nombre_producto"] not in seen_titles:
                    seen_titles.add(product_data["nombre_producto"])
                    products.append(product_data)
            if products:
                selector_used = product_sel
                break

    if not products:
        for h2 in soup.find_all("h2"):
            title_text = clean_text(h2.get_text())
            if title_text and len(title_text) > 5 and "$" in str(h2.parent):
                product_data = _extract_product_data(h2.parent, url)
                if product_data and product_data["nombre_producto"] not in seen_titles:
                    seen_titles.add(product_data["nombre_producto"])
                    products.append(product_data)

    if products:
        logger.debug(f"Extraidos {len(products)} productos usando selector {selector_used}", extra={"url": url})

    return products


# =============================================================================
# Strategy Interface
# =============================================================================
class ExtractionStrategy(ABC):
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this strategy handles the given URL."""
        pass

    @abstractmethod
    def extract_products(self, html: str, url: str) -> List[Dict[str, str]]:
        """Extract product list from HTML."""
        pass

    def discover_urls(self, html: str, url: str) -> List[str]:
        """Discover additional URLs to scrape (e.g. category pages)."""
        return []

    def has_pagination(self, html: str, url: str) -> bool:
        """Return True if the page has pagination."""
        return False

    def is_ajax_pagination(self, html: str, url: str) -> bool:
        """Return True if pagination is AJAX-based."""
        return False

    def get_total_pages(self, html: str, url: str) -> int:
        """Return total number of pages."""
        return 1

    def get_pagination_urls(self, url: str, max_pages: int) -> List[str]:
        """Return URL-based pagination links (page 2..N)."""
        return []

    async def fetch_ajax_pages(self, scraper, html: str, url: str, max_pages: int) -> List[str]:
        """Return list of HTML strings for AJAX pages. Override if needed."""
        return []


# =============================================================================
# Default / Generic Strategy
# =============================================================================
class DefaultStrategy(ExtractionStrategy):
    def can_handle(self, url: str) -> bool:
        return True  # fallback

    def extract_products(self, html: str, url: str) -> List[Dict[str, str]]:
        products = _generic_extract(html, url)
        if not products:
            logger.warning(f"No se encontraron productos con selectores estándar para {url}", extra={"url": url})
        return products

    def has_pagination(self, html: str, url: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        if soup.find(attrs={"data-totalpage": True}):
            return True
        if soup.select(".woocommerce-pagination a.page-number"):
            return True
        if soup.select(".pagination a, .page-numbers a"):
            return True
        return False

    def is_ajax_pagination(self, html: str, url: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        return bool(soup.find(attrs={"data-totalpage": True}))

    def get_total_pages(self, html: str, url: str) -> int:
        soup = BeautifulSoup(html, "lxml")
        elem = soup.find(attrs={"data-totalpage": True})
        if elem:
            return int(elem.get("data-totalpage", 1))
        page_links = soup.select(".woocommerce-pagination a.page-number")
        if page_links:
            numbers = []
            for link in page_links:
                try:
                    numbers.append(int(link.get_text(strip=True)))
                except ValueError:
                    pass
            return max(numbers) if numbers else 1
        return 1

    def get_pagination_urls(self, url: str, max_pages: int) -> List[str]:
        urls = []
        for page_num in range(2, max_pages + 1):
            urls.append(f"{url.rstrip('/')}/page/{page_num}/")
        return urls


# =============================================================================
# Emergente Strategy
# =============================================================================
class EmergenteStrategy(ExtractionStrategy):
    DOMAIN = "emergente.com.co"
    SITEMAP_URL = "https://www.emergente.com.co/product-sitemap.xml"

    def can_handle(self, url: str) -> bool:
        return self.DOMAIN in url

    def extract_products(self, html: str, url: str) -> List[Dict[str, str]]:
        if "/producto/" in url:
            return self._extract_single_product(html, url)
        return _generic_extract(html, url)

    def _extract_single_product(self, html: str, url: str) -> List[Dict[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        title_elem = soup.select_one("h1.product_title") or soup.select_one("h1.entry-title")
        price_elem = soup.select_one("p.price") or soup.select_one("span.woocommerce-Price-amount")

        title = clean_text(title_elem.get_text()) if title_elem else None
        price = None
        if price_elem:
            parsed = parse_price(price_elem.get_text())
            if parsed:
                price = f"$ {parsed}"

        if title:
            return [{
                "nombre_pagina": _extract_domain(url),
                "link": url,
                "nombre_producto": title,
                "precio": price or "",
            }]
        return []

    def discover_urls(self, html: str, url: str) -> List[str]:
        """If this is the shop landing, discover all product URLs via sitemap."""
        if "/producto/" in url:
            return []
        # Try to use sitemap
        return [self.SITEMAP_URL]

    def parse_sitemap(self, xml_html: str, base_url: str) -> List[str]:
        """Parse product-sitemap.xml and return list of product URLs."""
        soup = BeautifulSoup(xml_html, "xml")
        urls = []
        for loc in soup.find_all("loc"):
            text = loc.get_text()
            if "/producto/" in text:
                urls.append(text)
        logger.info(f"Emergente: sitemap contiene {len(urls)} productos", extra={"url": base_url})
        return urls

    def has_pagination(self, html: str, url: str) -> bool:
        if "/producto/" in url:
            return False
        soup = BeautifulSoup(html, "lxml")
        return bool(soup.find("nav", attrs={"data-totalpage": True}))

    def is_ajax_pagination(self, html: str, url: str) -> bool:
        return self.has_pagination(html, url)

    def get_total_pages(self, html: str, url: str) -> int:
        soup = BeautifulSoup(html, "lxml")
        nav = soup.find("nav", attrs={"data-totalpage": True})
        if nav:
            return int(nav.get("data-totalpage", 1))
        return 1

    async def fetch_ajax_pages(self, scraper, html: str, url: str, max_pages: int) -> List[str]:
        """
        AJAX pagination on Emergente is session-bound and doesn't work with
        stateless scrapers. The recommended approach is scraping via sitemap.
        """
        return []


# =============================================================================
# Ingesolar Strategy
# =============================================================================
class IngesolarStrategy(ExtractionStrategy):
    DOMAIN = "ingesolar.com.co"
    LANDING_PATH = "/productos/tienda/"

    def can_handle(self, url: str) -> bool:
        return self.DOMAIN in url

    def extract_products(self, html: str, url: str) -> List[Dict[str, str]]:
        products = _generic_extract(html, url)
        if not products:
            logger.warning(f"Ingesolar: no se encontraron productos en {url}", extra={"url": url})
        return products

    def discover_urls(self, html: str, url: str) -> List[str]:
        """
        The /productos/tienda/ page is a category landing with no direct products.
        Discover real category URLs from the grid links.
        """
        if self.LANDING_PATH not in url:
            return []

        soup = BeautifulSoup(html, "lxml")
        discovered = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/categoria-producto/" in href:
                discovered.add(urljoin(url, href))

        urls = sorted(discovered)
        if urls:
            logger.info(f"Ingesolar: descubiertas {len(urls)} categorías desde landing", extra={"url": url})
        return urls

    def has_pagination(self, html: str, url: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        return bool(soup.select(".woocommerce-pagination .page-numbers"))

    def get_total_pages(self, html: str, url: str) -> int:
        soup = BeautifulSoup(html, "lxml")
        nav = soup.select_one(".woocommerce-pagination")
        if nav:
            numbers = []
            for a in nav.find_all("a", class_="page-numbers"):
                try:
                    numbers.append(int(a.get_text(strip=True)))
                except ValueError:
                    pass
            return max(numbers) if numbers else 1
        return 1

    def get_pagination_urls(self, url: str, max_pages: int) -> List[str]:
        urls = []
        for page_num in range(2, max_pages + 1):
            separator = "&" if "?" in url else "?"
            urls.append(f"{url}{separator}product-page={page_num}")
        return urls


# =============================================================================
# Ineldec Strategy
# =============================================================================
class IneldecStrategy(ExtractionStrategy):
    DOMAIN = "ineldec.com"

    # WoodMart theme selectors
    PRODUCT_SELECTORS = [
        ".product-grid-item.product.type-product",
        ".wd-product.product.type-product",
    ]

    TITLE_SELECTORS = [
        "h3.wd-entities-title a",
        "h3.product-title a",
        ".wd-entities-title a",
    ]

    PRICE_SELECTORS = [
        "span.price .woocommerce-Price-amount",
        "span.price",
        ".woocommerce-Price-amount",
    ]

    LINK_SELECTORS = [
        "a.product-image-link",
        "h3.wd-entities-title a",
    ]

    def can_handle(self, url: str) -> bool:
        return self.DOMAIN in url

    def extract_products(self, html: str, url: str) -> List[Dict[str, str]]:
        products = _generic_extract(
            html, url,
            product_selectors=self.PRODUCT_SELECTORS,
            title_selectors=self.TITLE_SELECTORS,
            price_selectors=self.PRICE_SELECTORS,
            link_selectors=self.LINK_SELECTORS,
        )
        if not products:
            logger.warning(f"Ineldec: no se encontraron productos en {url}", extra={"url": url})
        return products

    def has_pagination(self, html: str, url: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        return bool(soup.select("nav.woocommerce-pagination"))

    def get_total_pages(self, html: str, url: str) -> int:
        soup = BeautifulSoup(html, "lxml")
        nav = soup.select_one("nav.woocommerce-pagination")
        if nav:
            numbers = []
            for a in nav.find_all("a", class_="page-numbers"):
                try:
                    numbers.append(int(a.get_text(strip=True)))
                except ValueError:
                    pass
            return max(numbers) if numbers else 1
        return 1

    def get_pagination_urls(self, url: str, max_pages: int) -> List[str]:
        urls = []
        for page_num in range(2, max_pages + 1):
            urls.append(f"{url.rstrip('/')}/page/{page_num}/")
        return urls


# =============================================================================
# Registry
# =============================================================================
_STRATEGIES: List[ExtractionStrategy] = [
    EmergenteStrategy(),
    IngesolarStrategy(),
    IneldecStrategy(),
]


def get_strategy_for_url(url: str) -> ExtractionStrategy:
    for strategy in _STRATEGIES:
        if strategy.can_handle(url):
            return strategy
    return DefaultStrategy()

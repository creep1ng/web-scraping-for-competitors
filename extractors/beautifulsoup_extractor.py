from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import re


PRODUCT_SELECTORS = [
    "li.product",
    "li.type-product",
    ".products .product",
    ".wc-block-grid__product",
    ".eael-product-wrap",
]

TITLE_SELECTORS = [
    "h2.woocommerce-loop-product__title",
    "h2.product-title",
    ".woocommerce-LoopProduct-link h2",
    ".product-details-wrap h2",
]

PRICE_SELECTORS = [
    ".woocommerce-Price-amount",
    ".price .amount",
    ".eael-product-price",
    "span.woocommerce-Price-amount",
]

LINK_SELECTORS = [
    "a.woocommerce-LoopProduct-link",
    "a.product-link",
    ".woocommerce-LoopProduct-link",
]


def parse_price(text: str) -> Optional[str]:
    text = text.strip()
    match = re.search(r'\$?\s*([\d.,]+)', text)
    if match:
        return match.group(1).replace(',', '.')
    return None


def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def extract_products_from_html(html: str, url: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")

    products = []
    seen_titles = set()

    for product_sel in PRODUCT_SELECTORS:
        product_elems = soup.select(product_sel)
        if product_elems:
            for product_elem in product_elems:
                product_data = _extract_product_data(product_elem, url)
                if product_data and product_data["nombre_producto"] not in seen_titles:
                    seen_titles.add(product_data["nombre_producto"])
                    products.append(product_data)
            if products:
                break

    if not products:
        for h2 in soup.find_all("h2"):
            title_text = clean_text(h2.get_text())
            if title_text and len(title_text) > 5 and "$" in str(h2.parent):
                product_data = _extract_product_data(h2.parent, url)
                if product_data and product_data["nombre_producto"] not in seen_titles:
                    seen_titles.add(product_data["nombre_producto"])
                    products.append(product_data)

    return products


def _extract_product_data(element, base_url: str) -> Optional[Dict[str, str]]:
    title = None
    link = None
    price = None

    for selector in TITLE_SELECTORS:
        title_elem = element.select_one(selector)
        if title_elem:
            title = clean_text(title_elem.get_text())
            break

    if not title:
        h2 = element.find("h2")
        if h2:
            title = clean_text(h2.get_text())

    if not title or len(title) < 3:
        return None

    for selector in LINK_SELECTORS:
        link_elem = element.select_one(selector)
        if link_elem and link_elem.get("href"):
            link = link_elem.get("href")
            break

    if not link:
        anchor = element.find("a", href=True)
        if anchor:
            link = anchor.get("href")

    for selector in PRICE_SELECTORS:
        price_elem = element.select_one(selector)
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            if price_text:
                parsed = parse_price(price_text)
                if parsed:
                    price = f"$ {parsed}"
                    break

    if not price:
        price_texts = element.find_all(text=lambda t: t and "$" in str(t))
        for pt in price_texts:
            parsed = parse_price(pt)
            if parsed:
                price = f"$ {parsed}"
                break

    # Prefer sale price (ins) over original price (del) if both exist
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


def _extract_domain(url: str) -> str:
    match = re.search(r'(?:https?://)?(?:www\.)?([^/]+)', url)
    return match.group(1) if match else url


def get_pagination_info(html: str) -> Dict[str, any]:
    soup = BeautifulSoup(html, "lxml")

    pagination_info = {
        "total_pages": 1,
        "has_pagination": False,
        "ajax_pagination": False,
    }

    pagination_elem = soup.find(attrs={"data-totalpage": True})
    if pagination_elem:
        pagination_info["has_pagination"] = True
        pagination_info["ajax_pagination"] = True
        pagination_info["total_pages"] = int(pagination_elem.get("data-totalpage", 1))
        pagination_info["products_per_page"] = int(pagination_elem.get("data-plimit", 12))
        return pagination_info

    page_links = soup.select(".woocommerce-pagination a.page-number")
    if page_links:
        pagination_info["has_pagination"] = True
        page_numbers = []
        for link in page_links:
            try:
                page_numbers.append(int(link.get_text(strip=True)))
            except ValueError:
                pass
        if page_numbers:
            pagination_info["total_pages"] = max(page_numbers)
        return pagination_info

    nav_links = soup.select(".pagination a, .page-numbers a")
    if nav_links:
        pagination_info["has_pagination"] = True

    return pagination_info

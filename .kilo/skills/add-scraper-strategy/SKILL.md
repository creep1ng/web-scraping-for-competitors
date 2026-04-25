---
name: add-scraper-strategy
description: >
  Use this skill whenever the user needs to add a new competitor website 
  to the scraping pipeline, create a new extraction strategy, fix "0 products found" 
  errors, or adapt selectors for a new e-commerce site. This includes any request 
  to scrape a new domain, troubleshoot why a site returns empty results, add pagination 
  support for a new site, or modify the existing strategy pattern in the web scraping 
  project. Also use this when the user mentions WooCommerce, WordPress, sitemaps, 
  AJAX pagination, or custom e-commerce themes.
---

# Añadir una nueva estrategia de scraping

Este proyecto usa un **patrón Strategy** en `extractors/strategies.py`. Cada sitio de e-commerce tiene su propia estrategia porque los selectores, la paginación y el descubrimiento de URLs varían entre dominios.

## Estructura del sistema

```
extractors/
├── beautifulsoup_extractor.py   # Helpers y selectores WooCommerce genéricos
├── strategies.py                # Interfaz Strategy + estrategias por dominio
└── __init__.py                  # Exporta get_strategy_for_url()
```

```
scrapers/
├── base.py                      # BaseScraper (fetch + request opcional)
├── cloudflare_scraper.py        # Remoto, stateless, no soporta clicks
├── local_playwright_scraper.py  # Local, soporta clicks y navegación JS
└── __init__.py                  # Factory get_scraper()
```

## Paso a paso para añadir un nuevo sitio

### Paso 1: Investigar el sitio manualmente

NUNCA asumas que un sitio es WooCommerce estándar. Investiga primero:

```bash
# 1. Ver HTML crudo (sin JS)
curl -s -L -A "Mozilla/5.0" "https://nuevo-sitio.com/tienda/" | grep -oP '<(div|li|a|h2|span)[^>]*class="[^"]*(?:product|price|title)[^"]*"[^>]*>' | head -30

# 2. Ver con Playwright (HTML renderizado)
python -c "
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://nuevo-sitio.com/tienda/', wait_until='networkidle')
        await page.wait_for_timeout(4000)
        html = await page.content()
        soup = BeautifulSoup(html, 'lxml')
        # Buscar contenedores de producto
        for tag in soup.find_all(True):
            cls = ' '.join(tag.get('class', []))
            if 'product' in cls.lower() and tag.name in ('div', 'li'):
                print(tag.name, cls[:80])
        await browser.close()
asyncio.run(main())
"
```

**Preguntas clave a responder:**
- ¿Los productos están en el HTML inicial o se cargan con AJAX/JS?
- ¿Cuál es el selector CSS del contenedor de producto?
- ¿Dónde está el título, precio y link dentro de ese contenedor?
- ¿Hay paginación? ¿Es por URL (`/page/2/`), query param (`?page=2`), o AJAX?
- ¿La URL inicial es una tienda con productos, o una landing de categorías?

### Paso 2: Crear la clase de estrategia

Edita `extractors/strategies.py` y añade una nueva clase que herede de `ExtractionStrategy`:

```python
class NuevoSitioStrategy(ExtractionStrategy):
    DOMAIN = "nuevo-sitio.com"

    # Selectores específicos del tema
    PRODUCT_SELECTORS = [
        "li.product",
        ".product.type-product",
    ]
    TITLE_SELECTORS = [
        "h2.woocommerce-loop-product__title",
    ]
    PRICE_SELECTORS = [
        ".woocommerce-Price-amount",
    ]
    LINK_SELECTORS = [
        "a.woocommerce-LoopProduct-link",
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
            logger.warning(f"NuevoSitio: no se encontraron productos en {url}", extra={"url": url})
        return products

    def discover_urls(self, html: str, url: str) -> List[str]:
        """Solo si la landing no tiene productos directos."""
        return []

    def has_pagination(self, html: str, url: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        return bool(soup.select(".woocommerce-pagination"))

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
            # Ajusta el formato según el sitio:
            # urls.append(f"{url.rstrip('/')}/page/{page_num}/")
            # urls.append(f"{url}?product-page={page_num}")
            urls.append(f"{url.rstrip('/')}/page/{page_num}/")
        return urls
```

### Paso 3: Registrar la estrategia

Añade la instancia a `_STRATEGIES` en `extractors/strategies.py`:

```python
_STRATEGIES: List[ExtractionStrategy] = [
    EmergenteStrategy(),
    IngesolarStrategy(),
    IneldecStrategy(),
    NuevoSitioStrategy(),  # <-- aquí
]
```

### Paso 4: Añadir la URL a `urls.txt`

```
https://nuevo-sitio.com/tienda/
```

### Paso 5: Probar

```bash
uv run main.py
```

## Troubleshooting: errores comunes y soluciones

### "0 productos encontrados"

**Causa más probable**: selectores incorrectos o la página no tiene productos en el HTML inicial.

**Diagnóstico:**
```bash
# Ver si hay productos en el HTML
curl -s -L -A "Mozilla/5.0" "URL" | grep -i "product" | head -20
```

**Soluciones:**
1. **Si el sitio usa JS para cargar productos**: necesitas Playwright local (`SCRAPER_ENGINE=local`). El scraper Cloudflare es stateless y puede no ejecutar JS complejo.
2. **Si es una landing de categorías** (como ingesolar.com.co): implementa `discover_urls()` para extraer links de categorías reales.
3. **Si los selectores son de un tema custom**: inspecciona el HTML renderizado con Playwright y actualiza `PRODUCT_SELECTORS`, `TITLE_SELECTORS`, etc.

### AttributeError: 'CloudflareScraper' object has no attribute 'fetch_with_pagination_click'

**Causa**: El código intenta usar clicks de paginación AJAX pero el scraper activo no los soporta.

**Solución en `main.py`:**
```python
if hasattr(scraper, 'fetch_with_pagination_click'):
    # usar clicks
else:
    logger.warning("Paginacion AJAX no soportada por este scraper")
```

La estrategia también puede implementar `fetch_ajax_pages()` como fallback, pero con scrapers stateless usualmente falla.

**Alternativas para paginación AJAX:**
- **Sitemap XML**: muchos sitios WooCommerce exponen `/product-sitemap.xml` o `/sitemap.xml`
- **Query params**: probar `?paged=2`, `?page=2`, `?product-page=2`
- **URL-based**: `/page/2/`, `/shop/page/2/`
- **Playwright local**: si todo lo demás falla, usar `SCRAPER_ENGINE=local`

### Paginación devuelve siempre los mismos productos

**Causa**: los clicks AJAX no funcionan; el HTML nunca cambia después del "click".

**Diagnóstico:**
```python
# Comparar hashes de contenido entre página 1 y 2
import hashlib
hash1 = hashlib.md5(html1.encode()).hexdigest()[:8]
hash2 = hashlib.md5(html2.encode()).hexdigest()[:8]
print(hash1, hash2)  # Si son iguales, la paginación no funcionó
```

**Soluciones:**
- Usar query params en lugar de clicks
- Capturar la petición AJAX real con Playwright (`page.on('request', ...)`)
- Usar sitemap como fallback

### Productos extraídos son menús o widgets, no productos reales

**Causa**: los selectores son demasiado amplios (ej: `li.product` también coincide con items del menú).

**Solución**: usa selectores más específicos:
```python
# Malo (demasiado amplio)
PRODUCT_SELECTORS = ["li.product"]

# Bueno (específico al grid de productos)
PRODUCT_SELECTORS = [
    ".products li.product",           # WooCommerce estándar
    ".wd-product.product.type-product",  # WoodMart
    ".eael-product-wrap",             # Essential Addons
]
```

También verifica que el contenedor tenga un precio (`$`) antes de aceptarlo como producto.

### "No se pudo obtener HTML" / errores de fetch

**Causas comunes:**
1. **URL mal formada** en `.env` (`CLOUDFLARE_WORKER_URL` sin `https://`)
2. **Worker caído** o bloqueado por el sitio destino
3. **Cloudflare 520** en el sitio destino (error intermitente del servidor)

**Soluciones:**
- Verificar que `CLOUDFLARE_WORKER_URL` incluya el protocolo (`https://`)
- Cambiar a `SCRAPER_ENGINE=local` como fallback
- Añadir reintentos con backoff exponencial
- Verificar logs en `logs/scraper_info.log`

### Muchos productos duplicados en el output

**Causa**: paginación que no avanza (siempre devuelve página 1) o URLs duplicadas en `urls.txt`.

**Solución:**
- `main.py` ya deduplica por `link` antes de exportar. Si aún hay duplicados, verifica que las URLs de paginación sean distintas.
- Asegúrate de que `get_pagination_urls()` no devuelva la misma URL repetida.

### Precios no se extraen o están vacíos

**Causa**: el sitio usa un formato de precio inusual o el precio está oculto hasta hover/click.

**Soluciones:**
- Revisar si el precio está dentro de `<ins>` (precio de oferta) vs `<del>` (precio original)
- El extractor ya busca `ins` como fallback, pero si el sitio usa otro tag, añade el selector a `PRICE_SELECTORS`
- Si el precio carga por JS, usar Playwright local

## Buenas prácticas

1. **Investiga antes de codear**: no asumas WooCommerce estándar. Usa Playwright para ver el HTML renderizado.
2. **Usa selectores específicos**: evita `li.product` solo; añade contexto (`.products li.product`).
3. **Limita MAX_PAGES_PER_URL**: las categorías grandes pueden tener 50+ páginas. Usa `.env` para controlar.
4. **Soporta fallback**: si la paginación AJAX falla, la estrategia puede devolver [] y `main.py` usará solo página 1.
5. **No hardcodees nonces**: los nonces de WordPress son por sesión; no intentes replicar POSTs AJAX sin sesión activa.
6. **Usa `logger.warning()` para estrategias**: cuando no se encuentran productos, loguea con el nombre de la estrategia para facilitar debugging.
7. **Prueba con una sola URL primero**: pon solo la nueva URL en `urls.txt` antes de correr todo el lote.

## Ejemplo completo: WoodMart (Ineldec)

Ineldec usa el tema WoodMart. Los productos están en:

```html
<div class="wd-product wd-hover-button wd-col product-grid-item product type-product">
  <div class="product-wrapper">
    <a class="product-image-link" href="...">
    <h3 class="wd-entities-title">
      <a href="...">Nombre del producto</a>
    </h3>
    <span class="price">
      <span class="woocommerce-Price-amount">
        <bdi>$ 850.000</bdi>
      </span>
    </span>
  </div>
</div>
```

Por eso `IneldecStrategy` usa:
```python
PRODUCT_SELECTORS = [
    ".product-grid-item.product.type-product",
    ".wd-product.product.type-product",
]
TITLE_SELECTORS = ["h3.wd-entities-title a"]
PRICE_SELECTORS = ["span.price .woocommerce-Price-amount"]
LINK_SELECTORS = ["a.product-image-link"]
```

## Referencias rápidas

| Problema | Check rápido |
|----------|-------------|
| ¿Es WooCommerce? | Buscar `woocommerce` en el HTML |
| ¿Tiene sitemap? | `curl https://sitio.com/product-sitemap.xml` |
| ¿Paginación por URL? | Probar `/page/2/` y ver si cambia el contenido |
| ¿Paginación por query? | Probar `?paged=2`, `?page=2`, `?product-page=2` |
| ¿Carga productos por JS? | Comparar `curl` vs Playwright renderizado |
| ¿Nonce en paginación? | Buscar `data-nonce` o `security` en el HTML |

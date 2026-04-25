# Web Scraping for Competitors

Sistema de scraping asíncrono para extraer productos de sitios de e-commerce de competidores en el sector de energía solar.

## Arquitectura

- **Motores de Scraping**: Cloudflare Worker (remoto) o Playwright (local)
- **Extracción**: BeautifulSoup con patrón **Strategy** (una estrategia por dominio)
- **Concurrency**: asyncio con semáforo configurable
- **Output**: CSV y Excel con deduplicación automática por URL

## Estructura

```
├── main.py                          # Orquestador principal
├── urls.txt                         # URLs iniciales a procesar
├── scrapers/
│   ├── base.py                      # Interfaz abstracta BaseScraper
│   ├── local_playwright_scraper.py  # Motor local con Playwright
│   ├── cloudflare_scraper.py        # Motor remoto vía Cloudflare Worker
│   └── __init__.py                  # Factory get_scraper()
├── extractors/
│   ├── beautifulsoup_extractor.py   # Selectores y helpers genéricos WooCommerce
│   ├── strategies.py                # Patrón Strategy por dominio
│   └── __init__.py
├── logger.py                        # Logger estructurado con debug opcional
├── .env                             # Configuración (no commitear)
├── resultados_competidores.csv      # Salida
└── resultados_competidores.xlsx     # Salida
```

## Patrón Strategy

Cada sitio tiene comportamientos distintos de markup, paginación y descubrimiento. En vez de selectores globales, usamos estrategias especializadas registradas en `extractors/strategies.py`:

| Estrategia | Sitio | Problemática resuelta |
|---|---|---|
| `EmergenteStrategy` | emergente.com.co | Paginación AJAX con nonce de sesión (no replicable stateless). Se usa sitemap XML + scraping de producto individual. |
| `IngesolarStrategy` | ingesolar.com.co | La URL `/productos/tienda/` es una landing de categorías sin productos. Descubre automáticamente las categorías reales (`/categoria-producto/...`). Paginación vía `?product-page=N`. |
| `IneldecStrategy` | ineldec.com | Usa tema WoodMart con selectores distintos (`.wd-product`, `h3.wd-entities-title a`). Paginación vía `/page/N/`. |
| `DefaultStrategy` | Fallback | Selectores WooCommerce estándar (`li.product`, `.woocommerce-Price-amount`, etc.). |

### Cómo se selecciona la estrategia

```python
from extractors import get_strategy_for_url

strategy = get_strategy_for_url("https://www.emergente.com.co/...")
products = strategy.extract_products(html, url)
```

## Flujo de ejecución

1. **Descubrimiento** (`discover_urls`): Para cada URL inicial, la estrategia puede descubrir URLs adicionales.
   - Emergente: parsea `product-sitemap.xml` y devuelve todas las URLs de productos.
   - Ingesolar: parsea la landing y extrae los links de categorías.
   - Ineldec: no descubre nada adicional.

2. **Procesamiento** (`process_single_url`): Cada URL (inicial + descubiertas) se scrapea:
   - Fetch del HTML con el motor configurado (Cloudflare o Playwright local).
   - Extracción de productos con la estrategia correspondiente.
   - Paginación URL-based si aplica (`?product-page=N` o `/page/N/`).
   - Paginación AJAX solo si el scraper soporta clicks (Playwright local), sino se queda en página 1.

3. **Deduplicación**: Antes de guardar, se eliminan duplicados por `link`.

4. **Persistencia**: CSV + Excel.

## Estrategias detalladas

### Emergente (emergente.com.co)

- **Tienda**: Usa Essential Addons para Elementor con un product grid AJAX.
- **Paginación**: 353 páginas totales. Los clicks usan `admin-ajax.php` con un nonce dinámico vinculado a la sesión de WordPress.
- **Por qué no funciona AJAX stateless**: El nonce se genera por sesión y el servidor devuelve `-1` o `403` si se hace POST sin contexto de sesión válido.
- **Solución**: Se scrapea el sitemap XML (`product-sitemap.xml`) para obtener todas las URLs de productos (~300+), y cada producto se visita individualmente. El HTML de la página de producto contiene `h1.product_title` y `p.price` con la información completa.

### Ingesolar (ingesolar.com.co)

- **Tienda**: WooCommerce con tema Divi.
- **Landing**: `/productos/tienda/` no tiene productos. Es un grid de imágenes que lleva a categorías (`/categoria-producto/panel-solar-paneles-solares/`, etc.).
- **Descubrimiento**: La estrategia parsea todos los `<a href="/categoria-producto/...">` de la landing.
- **Paginación**: Usa query param `?product-page=2`, `?product-page=3`, etc. No usa `/page/N/`.
- **Categorías descubiertas**: 55 URLs únicas incluyendo subcategorías (paneles, baterías AGM/gel/litio, inversores on-grid/híbridos, bombas, calentadores, estructuras, etc.).

### Ineldec (ineldec.com)

- **Tienda**: WooCommerce con tema WoodMart.
- **Selectores**:
  - Contenedor: `.product-grid-item.product.type-product`
  - Título: `h3.wd-entities-title a`
  - Precio: `span.price .woocommerce-Price-amount`
  - Link: `a.product-image-link`
- **Paginación**: `/page/2/`, `/page/3/`, etc. Funciona correctamente con requests GET.

## Scrapers

### CloudflareScraper

Conecta con un Cloudflare Worker que recibe `{url, method, body, headers}` y devuelve el HTML renderizado.

Ventajas:
- No requiere instalar Playwright ni navegador local.
- Puede manejar sitios con protecciones básicas.

Limitaciones:
- Es stateless: sesiones, cookies y nonces no persisten entre requests.
- No soporta clicks ni interacciones complejas (solo navegación GET).

### LocalPlaywrightScraper

Usa `playwright.async_api` con Chromium headless. Soporta:
- Navegación con `wait_until="networkidle"`.
- Clicks de paginación AJAX (`fetch_with_pagination_click`).
- Requests POST genéricos vía `page.evaluate(fetch(...))`.

## Configuración

Crear archivo `.env`:

```env
SCRAPER_ENGINE=cloudflare          # o "local"
CLOUDFLARE_WORKER_URL=https://...
CLOUDFLARE_API_TOKEN=...
MAX_CONCURRENCY=5
MAX_PAGES_PER_URL=10
MAX_SITEMAP_PRODUCTS=300           # límite de productos Emergente desde sitemap
DEBUG=true
```

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `SCRAPER_ENGINE` | Motor: `local` (Playwright) o `cloudflare` (Worker remoto) | `local` |
| `MAX_CONCURRENCY` | Tareas paralelas | `3` |
| `MAX_PAGES_PER_URL` | Páginas máximas por URL (paginación) | `5` |
| `MAX_SITEMAP_PRODUCTS` | Límite de productos Emergente desde sitemap | `300` |
| `CLOUDFLARE_WORKER_URL` | Endpoint del Worker | - |
| `CLOUDFLARE_API_TOKEN` | Token Bearer para autenticar Worker | - |

## Uso

1. Configurar `.env`
2. Crear `urls.txt` con una URL por línea (pueden ser landings de tienda).
3. Ejecutar:

```bash
uv run main.py
```

## Estado Actual (25-Abr-2026)

### Funcionando
- ✅ Emergente: 311 productos extraídos vía sitemap + páginas de producto.
- ✅ Ingesolar: 492 productos únicos extraídos de 55 categorías/subcategorías.
- ✅ Ineldec: 120 productos extraídos con selectores WoodMart.
- ✅ Deduplicación global por URL antes de exportar.

### Limitaciones conocidas
- Emergente: la paginación AJAX no funciona con scraper stateless (Cloudflare). Se usa sitemap como workaround.
- Algunos productos no tienen precio listado (aparecen como `NaN` o vacío); suelen ser productos bajo cotización.
- Ingesolar tiene categorías vacías (`movilidad-electrica`) que devuelven 0 productos.

### Scripts de debug mantenidos
- `debug_prices.py`
- `investigate_pagination.py`

## Próximos pasos sugeridos

1. **Aumentar límite de sitemap**: Subir `MAX_SITEMAP_PRODUCTS` si el worker de Cloudflare soporta más requests.
2. **Paginación Ingesolar**: Algunas categorías tienen más de 10 páginas. Aumentar `MAX_PAGES_PER_URL` para obtener más productos.
3. **Worker con Puppeteer**: Migrar el Cloudflare Worker a Puppeteer para soportar clicks AJAX y no depender del sitemap.
4. **Más sitios**: Registrar nuevas estrategias para competidores adicionales sin modificar `main.py`.

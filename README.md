# Web Scraping for Competitors

Sistema de scraping asíncrono para extraer productos de sitios de e-commerce de competidores.

## Arquitectura

- **Motores de Scraping**: Cloudflare Worker (remoto) o Playwright (local)
- **Extracción**: BeautifulSoup (directa, sin LLM) para mejor velocidad y costo
- **Concurrency**: asyncio con semaforo configurable
- **Output**: CSV y Excel

## Estructura

```
├── main.py                          # Orquestador principal
├── scrapers/
│   ├── base.py                      # Interfaz abstracta
│   ├── local_playwright_scraper.py  # Motor local con Playwright
│   ├── cloudflare_scraper.py        # Motor remoto via Worker
│   └── __init__.py
├── extractors/
│   ├── beautifulsoup_extractor.py   # Extracción directa de productos
│   └── __init__.py
├── scrapers/                        # Módulos de scraping
├── requirements.txt
└── .env                             # Configuración (no committing)
```

## Uso

1. Configurar `.env`:
```env
SCRAPER_ENGINE=local
MAX_CONCURRENCY=3
MAX_PAGES_PER_URL=5
OPENROUTER_API_KEY=your_key_here
LLM_MODEL=inclusionai/ling-2.6-1t:free
```

2. Crear `urls.txt` con una URL por línea

3. Ejecutar:
```bash
python main.py
```

## Estado Actual (25-Abr-2026)

### Problema Conocido: Paginación AJAX

El sitio `emergente.com.co` usa Essential Addons para WordPress con paginación AJAX que **no funciona correctamente** desde contexto headless automation.

**Síntomas:**
- La página 1 se extrae correctamente (12 productos)
- Los clicks de paginación se ejecutan sin error
- Sin embargo, las páginas 2-10 contienen el **mismo contenido** que la página 1

**Investigación realizada:**
- Confirmado que `networkidle` + jQuery trigger sí funciona en pruebas manuales del navegador
- Los clicks se ejecutan sin errores de JavaScript
- No se capturan requests AJAX durante la paginación (posible bloqueo o condición de carrera)

**Soluciones alternativas no implementadas:**
1. Cloudflare Worker con Puppeteer (más robusto para JS complejo)
2. Selenium/SeleniumBase como alternativa
3. Espera más larga o reintentos con verificación de contenido

### Scripts de Debug

Los siguientes scripts fueron creados durante la investigación y se mantienen por si son útiles para debugging futuro:

- `debug_prices.py` - Analizó la estructura de precios de WooCommerce (descubrió que los precios de oferta están en `<ins>` y los originales en `<del>`)
- `investigate_pagination.py` - Investigó el comportamiento de la paginación AJAX
- `investigate_click.py` - Comparó diferentes métodos de click (querySelector, locator, jQuery trigger, dispatchEvent)

Estos archivos están ignorados por `.gitignore` para mantener limpio el repositorio.

## Configuración de Entorno

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| SCRAPER_ENGINE | `local` o `cloudflare` | `local` |
| MAX_CONCURRENCY | Tareas paralelas | 3 |
| MAX_PAGES_PER_URL | Páginas a scrapear por URL | 5 |
| CLOUDFLARE_WORKER_URL | URL del Worker (si engine=cloudflare) | - |
| CLOUDFLARE_API_TOKEN | Token del Worker | - |
| OPENROUTER_API_KEY | API key para OpenRouter | - |
| LLM_MODEL | Modelo para extracción (no usado actualmente) | `inclusionai/ling-2.6-1t:free` |

## Próximos Pasos Sugeridos

1. **Validar con otros sitios**: Probar el scraper con otros e-commerces para confirmar que el problema es específico de emergente.com.co
2. **Investigar Cloudflare Worker**: Implementar el worker de Puppeteer para sitios con JS complejo
3. **Detección de sitio específico**: Crear estrategia de paginación por sitio (ej: para emergente.com.co usar URL-based si disponible)
4. **Soporte LLM opcional**: Mantener la posibilidad de usar OpenRouter como fallback para sitios con estructura HTML impredecible
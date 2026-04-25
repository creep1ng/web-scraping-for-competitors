# Web Scraper de Competidores

Sistema de scraping asíncrono con motores intercambiables (Cloudflare Worker / Playwright local) y extracción de datos mediante LLMs.

## Requisitos

- Python 3.10+
- Node.js (para Cloudflare Worker, opcional)

## Instalación

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate   # Windows

pip install -r requirements.txt
playwright install chromium
```

## Configuración

Copia `.env.example` a `.env` y completa las credenciales:

```bash
cp .env.example .env
```

Variables disponibles:
- `SCRAPER_ENGINE`: `local` (default) o `cloudflare`
- `CLOUDFLARE_WORKER_URL`: URL del Worker de Cloudflare
- `CLOUDFLARE_API_TOKEN`: Token de API de Cloudflare
- `OPENROUTER_API_KEY`: Clave de API de OpenRouter
- `LLM_MODEL`: Modelo a usar (default: `stepfun/step-3.5-flash`)
- `MAX_CONCURRENCY`: Máximo de peticiones concurrentes (default: 10)

## Uso

1. Agrega las URLs a procesar en `urls.txt`
2. Ejecuta:

```bash
python main.py
```

Los resultados se exportarán a `resultados_competidores.csv` y `resultados_competidores.xlsx`.

## Deploy Cloudflare Worker (opcional)

```bash
npx wrangler deploy
```

Obtén la URL del endpoint y configúrala en `CLOUDFLARE_WORKER_URL`.

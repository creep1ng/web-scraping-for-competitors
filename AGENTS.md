# Web Scraper de Competidores

## Setup

```bash
pip install -r requirements.txt
playwright install chromium  # required for local scraper
cp .env.example .env
```

## Running

```bash
python main.py
```

Reads URLs from `urls.txt`, outputs to `resultados_competidores.csv` and `.xlsx`.

## Architecture

- `scrapers/base.py` + `get_scraper()` — factory pattern, swap engine via `SCRAPER_ENGINE=local|cloudflare`
- `extractor.py` — LLM extraction via OpenRouter (JSON structured output)
- `main.py` — asyncio orchestrator with semaphore concurrency

## Environment Variables

| Variable | Default | Notes |
|---|---|---|
| `SCRAPER_ENGINE` | `local` | `local` or `cloudflare` |
| `MAX_CONCURRENCY` | `10` | Semaphore limit |
| `LLM_MODEL` | `stepfun/step-3.5-flash` | OpenRouter model |

## Cloudflare Worker (optional)

```bash
npx wrangler deploy  # from repo root
```

Worker URL goes in `CLOUDFLARE_WORKER_URL`.

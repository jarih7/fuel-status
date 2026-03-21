# fuel-status

A GitHub Pages site that displays current Czech fuel prices (Natural 95 / Petrol 95 and standard Diesel) for Tank ONO stations across the Czech Republic.

## Live site

Once GitHub Pages is enabled for this repository, the site will be available at:
`https://<owner>.github.io/fuel-status/`

## Data source

Prices are scraped daily from **[tank-ono.cz](https://www.tank-ono.cz/cz/index.php?page=cenik)** — the official price list of the Tank ONO fuel station network (~45 stations across all Czech regions).

## How it works

| File | Purpose |
|------|---------|
| `index.html` | Static GitHub Pages site — sortable/filterable table of station prices |
| `data/prices.json` | Fuel price data updated daily by the scraper |
| `scripts/fetch_prices.py` | Python scraper targeting `tank-ono.cz/cz/index.php?page=cenik` |
| `scripts/requirements.txt` | Python dependencies (`requests`, `beautifulsoup4`, `lxml`) |
| `.github/workflows/update_prices.yml` | Daily GitHub Action (06:00 UTC) — runs scraper and commits updated JSON |
| `.github/workflows/pages.yml` | Deploys the site to GitHub Pages on every push to `main` |

## Setup

1. **Enable GitHub Pages** in repository Settings → Pages → Source: `GitHub Actions`.
2. The `pages.yml` workflow will deploy automatically.
3. Prices update every day at 06:00 UTC via the `update_prices.yml` workflow (or trigger it manually from the Actions tab).

## Running the scraper locally

```bash
pip install -r scripts/requirements.txt
python scripts/fetch_prices.py
```

This writes updated prices to `data/prices.json`.

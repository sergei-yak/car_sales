# Facebook Marketplace Car Scraper (Pyppeteer, Python)

This tool scrapes car listings from Facebook Marketplace using Pyppeteer (headless Chromium via DevTools protocol).

Important: Facebook Marketplace requires an authenticated session. Provide cookies exported from a logged-in browser profile.

## Setup

1. Python 3.10+
2. Install dependencies:

```bash
pip3 install --break-system-packages -r requirements.txt
# First run will auto-download a compatible Chromium (~100-150 MB)
```

## Export Cookies

- Use a browser extension (e.g., "Get cookies.txt" or "EditThisCookie") to export cookies while logged into Facebook.
- Save as JSON (array of cookie objects) or an object with a top-level `cookies` array.

## Usage

```bash
python3 -m scraper.cli --query "Toyota Camry" --max-items 40 --cookies ./cookies.json --out-json results.json --out-csv results.csv --headless
```

Outputs compact JSON to stdout and optionally writes JSON/CSV files.

Tips:
- If the script redirects to a login page, your cookies are missing/expired.
- Use `--slow-mo-ms 250` and `--headless false` for debugging.

## Fields per listing

- `item_id`
- `url`
- `title`
- `price_text`
- `location_text` (best-effort; may be empty from list view)
- `image_url`
- `scraped_at` (UTC ISO8601)

Note: Facebook’s DOM changes frequently; selectors use conservative, stable heuristics (links containing `/marketplace/item/`).

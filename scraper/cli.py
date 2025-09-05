import argparse
import json
import csv
from pathlib import Path
from typing import List, Dict

from .marketplace import scrape_marketplace_cars


def write_json(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def write_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with path.open("w", newline="", encoding="utf-8") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Facebook Marketplace car listings using Playwright. Requires login cookies.",
    )
    parser.add_argument("--query", required=True, help="Search query, e.g., 'Toyota Camry 2018' ")
    parser.add_argument("--max-items", type=int, default=50, help="Maximum number of listings to return")
    parser.add_argument("--cookies", type=str, default=None, help="Path to cookies JSON exported from your browser")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True, help="Run headless")
    parser.add_argument("--slow-mo-ms", type=int, default=0, help="Slow motion in milliseconds (debug)")
    parser.add_argument("--out-json", type=str, default=None, help="Write results to JSON at this path")
    parser.add_argument("--out-csv", type=str, default=None, help="Write results to CSV at this path")
    parser.add_argument("--save-cookies", type=str, default=None, help="Save session cookies to this file after run")

    args = parser.parse_args()

    rows = scrape_marketplace_cars(
        query=args.query,
        max_items=args.max_items,
        cookies_path=args.cookies,
        headless=bool(args.headless),
        slow_mo_ms=args.slow_mo_ms,
        save_cookies_to=args.save_cookies,
    )

    if args.out_json:
        write_json(Path(args.out_json), rows)
    if args.out_csv:
        write_csv(Path(args.out_csv), rows)

    # Always print compact JSON to stdout
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()

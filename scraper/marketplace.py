from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set

from tenacity import retry, stop_after_attempt, wait_fixed
from pyppeteer import launch


FACEBOOK_MARKETPLACE_SEARCH = "https://www.facebook.com/marketplace/search/?query={query}"
FACEBOOK_MARKETPLACE_HOME = "https://www.facebook.com/marketplace/"


@dataclass
class Listing:
    item_id: str
    url: str
    title: str
    price_text: str
    location_text: str
    image_url: str
    scraped_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_item_id_from_url(url: str) -> Optional[str]:
    match = re.search(r"/marketplace/item/(\d+)", url)
    return match.group(1) if match else None


def _default_user_agent() -> str:
    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


def _load_cookies_from_file(cookies_path: str) -> List[Dict]:
    with open(cookies_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "cookies" in data and isinstance(data["cookies"], list):
        return data["cookies"]
    if isinstance(data, list):
        return data
    raise ValueError("Unsupported cookies file format. Expect a JSON array or an object with a 'cookies' array.")


async def _save_cookies_to_file(page, cookies_path: str) -> None:
    cookies = await page.cookies()
    with open(cookies_path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)


async def _create_browser_page(
    *,
    headless: bool,
    slow_mo_ms: int,
    cookies_path: Optional[str],
    user_agent: Optional[str] = None,
):
    browser = await launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ],
        slowMo=slow_mo_ms,
        handleSIGINT=False,
        handleSIGTERM=False,
        handleSIGHUP=False,
    )
    page = await browser.newPage()
    await page.setUserAgent(user_agent or _default_user_agent())
    await page.setViewport({"width": 1366, "height": 900})
    if cookies_path and os.path.exists(cookies_path):
        try:
            cookies = _load_cookies_from_file(cookies_path)
            normalized = []
            for c in cookies:
                c = {**c}
                if "sameSite" in c and isinstance(c["sameSite"], str):
                    c["sameSite"] = c["sameSite"].capitalize()
                if not c.get("domain") and not c.get("url"):
                    c["domain"] = ".facebook.com"
                normalized.append(c)
            for c in normalized:
                await page.setCookie(c)
        except Exception:
            pass
    return browser, page


async def _is_login_page(page) -> bool:
    url = page.url or ""
    if "login" in url:
        return True
    try:
        el = await page.querySelector('input[name="email"]')
        return bool(el)
    except Exception:
        return False


async def _ensure_logged_in(page) -> None:
    await page.goto(FACEBOOK_MARKETPLACE_HOME, waitUntil="domcontentloaded")
    for _ in range(3):
        if not await _is_login_page(page):
            return
        await asyncio.sleep(1.0)
    if await _is_login_page(page):
        raise RuntimeError(
            "Facebook requires login to view Marketplace. Provide cookies file exported from a logged-in browser."
        )


def _build_search_url(query: str) -> str:
    from urllib.parse import quote

    return FACEBOOK_MARKETPLACE_SEARCH.format(query=quote(query))


def _unique_by_item_id(listings: Iterable[Listing]) -> List[Listing]:
    seen: Set[str] = set()
    unique: List[Listing] = []
    for l in listings:
        if l.item_id in seen:
            continue
        seen.add(l.item_id)
        unique.append(l)
    return unique


def _parse_anchor_map(record: Dict) -> Optional[Listing]:
    try:
        href = record.get("href") or ""
        if "/marketplace/item/" not in href:
            return None
        item_id = _extract_item_id_from_url(href)
        if not item_id:
            return None
        text_lines = [t.strip() for t in (record.get("text") or "").split("\n") if t.strip()]
        title = text_lines[0] if text_lines else ""
        price_text = ""
        for t in text_lines[1:3]:
            if any(s in t for s in ["$", "€", "£", "CAD", "AUD", "₹", "Price"]):
                price_text = t
                break
        return Listing(
            item_id=item_id,
            url=href,
            title=title,
            price_text=price_text,
            location_text="",
            image_url=record.get("img") or "",
            scraped_at=_now_iso(),
        )
    except Exception:
        return None


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def _scroll_once(page) -> None:
    await page.evaluate(
        "() => new Promise(resolve => { window.scrollBy(0, document.body.scrollHeight); setTimeout(resolve, 800); })"
    )


async def _collect_listings_from_page(page) -> List[Listing]:
    records: List[Dict] = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href*="/marketplace/item/"]')).map(a => ({
            href: a.href,
            text: a.innerText || '',
            img: (a.querySelector('img') || {}).src || ''
        }))
        """
    )
    results: List[Listing] = []
    for rec in records:
        listing = _parse_anchor_map(rec)
        if listing is not None:
            results.append(listing)
    return results


async def scrape_marketplace_cars_async(
    *,
    query: str,
    max_items: int = 50,
    cookies_path: Optional[str] = None,
    headless: bool = True,
    slow_mo_ms: int = 0,
    save_cookies_to: Optional[str] = None,
    location_contains: Optional[List[str]] = None,
) -> List[Dict]:
    browser = None
    page = None
    try:
        browser, page = await _create_browser_page(
            headless=headless, slow_mo_ms=slow_mo_ms, cookies_path=cookies_path
        )

        await _ensure_logged_in(page)

        search_url = _build_search_url(query)
        await page.goto(search_url, waitUntil="domcontentloaded")

        collected: List[Listing] = []
        attempts_without_growth = 0
        while len(collected) < max_items and attempts_without_growth < 8:
            current = await _collect_listings_from_page(page)
            before = len(collected)
            collected = _unique_by_item_id([*collected, *current])
            after = len(collected)
            if after >= max_items:
                break
            if after == before:
                attempts_without_growth += 1
            else:
                attempts_without_growth = 0
            await _scroll_once(page)

        # Optional location filtering by substring(s)
        if location_contains:
            needles = [s.strip().lower() for s in location_contains if s and s.strip()]
            collected = [l for l in collected if any(n in l.location_text.lower() for n in needles)]

        if save_cookies_to:
            try:
                await _save_cookies_to_file(page, save_cookies_to)
            except Exception:
                pass

        limited = collected[:max_items]
        return [asdict(l) for l in limited]
    finally:
        try:
            if page is not None:
                await page.close()
        except Exception:
            pass
        try:
            if browser is not None:
                await browser.close()
        except Exception:
            pass


def scrape_marketplace_cars(
    *,
    query: str,
    max_items: int = 50,
    cookies_path: Optional[str] = None,
    headless: bool = True,
    slow_mo_ms: int = 0,
    save_cookies_to: Optional[str] = None,
    location_contains: Optional[List[str]] = None,
) -> List[Dict]:
    return asyncio.run(
        scrape_marketplace_cars_async(
            query=query,
            max_items=max_items,
            cookies_path=cookies_path,
            headless=headless,
            slow_mo_ms=slow_mo_ms,
            save_cookies_to=save_cookies_to,
            location_contains=location_contains,
        )
    )

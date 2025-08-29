# scraper/test_logo_grab_playwright.py
# -*- coding: utf-8 -*-
"""
Render Huskers schedule with Playwright (Chromium), then extract opponent logos.

Outputs (all relative to repo root):
  - data/schedule_raw_rendered.html   (post-JS DOM snapshot)
  - data/opponent_logos_found.json    (opponent_name/slug/logo_url)
  - docs/assets/opponents/_fetched/*  (downloaded logo files if retrievable)

Run locally:
  pip install playwright requests beautifulsoup4 lxml
  python -m playwright install chromium
  python -m scraper.test_logo_grab_playwright
"""

from __future__ import annotations
import asyncio, json, re, sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# --- Paths ---
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
OUT_DIR = DOCS / "assets" / "opponents" / "_fetched"
for p in (DATA, OUT_DIR):
    p.mkdir(parents=True, exist_ok=True)

URL = "https://huskers.com/sports/football/schedule"


# --- Helpers ---
def slugify(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def first_from_srcset(s: str | None) -> str | None:
    if not s:
        return None
    # "url 1x, url2 2x" -> take first URL token
    return s.split(",")[0].strip().split(" ")[0]


def is_placeholder(u: str | None) -> bool:
    # ignore transparent data urls / placeholders
    return (not u) or u.startswith("data:image")


def ext_from(u: str) -> str:
    ext = Path(urlparse(u).path).suffix.lower()
    return ext if ext in (".svg", ".png", ".jpg", ".jpeg", ".webp") else ".svg"


# --- Main ---
async def main() -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright not installed. Do:\n"
              "  pip install playwright requests beautifulsoup4 lxml\n"
              "  python -m playwright install chromium")
        return 2

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124 Safari/537.36")
        )
        page = await ctx.new_page()

        # Load & let lazy stuff happen
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1200)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(400)

        # Snapshot rendered DOM
        html = await page.content()
        (DATA / "schedule_raw_rendered.html").write_text(html, encoding="utf-8")
        print("Saved: data/schedule_raw_rendered.html")

        soup = BeautifulSoup(html, "lxml")
        cards = (soup.select("div.schedule-event-item-default")
                 or soup.select("div.schedule-event-item")
                 or soup.select("li.schedule__list-item"))
        print(f"Rendered cards found: {len(cards)}")

        def extract_img(img) -> str | None:
            for k in ("data-src",):
                u = img.get(k)
                if u and not is_placeholder(u):
                    return u
            u = first_from_srcset(img.get("data-srcset")) or first_from_srcset(img.get("srcset"))
            if u and not is_placeholder(u):
                return u
            u = img.get("src")
            if u and not is_placeholder(u):
                return u
            return None

        rows = []
        for card in cards:
            # Opponent name
            on = (card.select_one(".schedule-event-item-default__opponent-name")
                  or card.select_one(".opponent,.team"))
            opp_name = on.get_text(" ", strip=True) if on else None
            opp_slug = slugify(opp_name)

            # Images: wrapper usually contains [Nebraska, Opponent] in that order
            wrap = card.select_one(".schedule-event-item-default__images")
            imgs = (wrap.find_all("img") if wrap else card.find_all("img"))

            logo_url = None
            if imgs:
                # assume last image is opponent (N first)
                cand = extract_img(imgs[-1])
                if cand:
                    logo_url = cand

            # Fallback: any image alt loosely matching opponent name (avoid "nebraska")
            if not logo_url and opp_name:
                on_cf = opp_name.casefold()
                for im in card.select("img[alt]"):
                    alt = (im.get("alt") or "").lower()
                    if not alt or "nebraska" in alt:
                        continue
                    a = slugify(alt)
                    if a == opp_slug or (opp_slug and (a in opp_slug or opp_slug in a)):
                        cand = extract_img(im)
                        if cand:
                            logo_url = cand
                            break

            rows.append({
                "opponent_name": opp_name,
                "opponent_slug": opp_slug,
                "logo_url": logo_url
            })

        # Write report
        (DATA / "opponent_logos_found.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print("Saved: data/opponent_logos_found.json")

        # Try to download logos so the site can use local files immediately
        saved = 0
        for r in rows:
            u, slug = r.get("logo_url"), r.get("opponent_slug")
            if not (u and slug):
                print(f"SKIP: {r.get('opponent_name')} → no logo URL")
                continue
            try:
                resp = requests.get(u, timeout=30)
                resp.raise_for_status()
                out = OUT_DIR / f"{slug}{ext_from(u)}"
                out.write_bytes(resp.content)
                saved += 1
                print(f"Downloaded {slug} → {out}")
            except Exception as e:
                print(f"Download failed for {slug}: {e}")

        await ctx.close()
        await browser.close()
        print(f"Done. Logos downloaded: {saved}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

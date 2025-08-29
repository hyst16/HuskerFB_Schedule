# -*- coding: utf-8 -*-
"""
Probe logos from https://huskers.com/sports/football/schedule
- Extracts opponent names + best-guess logo URLs (handles data-src/srcset/src)
- Writes a report: data/opponent_logos_found.json
- Optionally downloads each logo into docs/assets/opponents/_fetched/
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
OPP_DIR = DOCS / "assets" / "opponents" / "_fetched"
for p in (DATA, OPP_DIR):
    p.mkdir(parents=True, exist_ok=True)

URL = "https://huskers.com/sports/football/schedule"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (LogoProbe/1.0; +https://example.com)"
}

def first_from_srcset(s: str | None) -> str | None:
    if not s:
        return None
    # "url 1x, url 2x" → take first URL
    return s.split(",")[0].strip().split(" ")[0]

def get_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def clean_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")

def is_placeholder(u: str | None) -> bool:
    # ignore transparent 1x1 gifs/data urls
    if not u:
        return True
    return u.startswith("data:image")

def find_card_blocks(soup: BeautifulSoup):
    # WMT cards that include logos/opponents:
    # container: .schedule-event-item-default
    return soup.select("div.schedule-event-item-default")

def extract_logo_url_from_img(img) -> str | None:
    # Modern sites often lazy-load with data-src or srcset
    for key in ("data-src",):
        v = img.get(key)
        if v and not is_placeholder(v):
            return v
    for key in ("data-srcset", "srcset"):
        v = first_from_srcset(img.get(key))
        if v and not is_placeholder(v):
            return v
    v = img.get("src")
    if v and not is_placeholder(v):
        return v
    return None

def probe() -> list[dict]:
    html = get_html(URL)
    soup = BeautifulSoup(html, "lxml")

    results = []
    for card in find_card_blocks(soup):
        # Opponent name
        on_el = card.select_one(".schedule-event-item-default__opponent-name")
        opp_name = clean_text(on_el.get_text()) if on_el else None
        opp_slug = slugify(opp_name) if opp_name else None

        # Team images block: usually [Nebraska, Opponent] → last is opponent
        logo_url = None
        imgs = card.select(".schedule-event-item-default__images img")
        if imgs:
            opp_img = imgs[-1]
            logo_url = extract_logo_url_from_img(opp_img)

        # Fallback: fuzzy alt match (ignore any alt that includes "nebraska")
        if not logo_url and opp_name:
            for im in card.select("img[alt]"):
                alt = clean_text(im.get("alt"))
                if not alt:
                    continue
                if "nebraska" in alt.lower():
                    continue
                a = slugify(alt)
                if a == opp_slug or opp_slug in a or a in opp_slug:
                    logo_url = extract_logo_url_from_img(im)
                    if logo_url:
                        break

        results.append({
            "opponent_name": opp_name,
            "opponent_slug": opp_slug,
            "logo_url": logo_url
        })

    return results

def download_logo(url: str, dest_path: Path) -> bool:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        dest_path.write_bytes(r.content)
        return True
    except Exception:
        return False

def choose_ext(url: str) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    # normalize some cases
    if ext in (".svg", ".png", ".jpg", ".jpeg", ".webp"):
        return ext
    # default to .svg (huskers uses many svg logos)
    return ".svg"

def main() -> int:
    rows = probe()

    # Write the report (always)
    report_path = DATA / "opponent_logos_found.json"
    report_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote report: {report_path.relative_to(ROOT)}")

    # Try to download each logo we found (optional test)
    downloaded = 0
    for row in rows:
        name = row.get("opponent_name")
        slug = row.get("opponent_slug")
        url = row.get("logo_url")
        if not (slug and url):
            print(f"SKIP: {name} → no logo URL")
            continue
        ext = choose_ext(url)
        out = OPP_DIR / f"{slug}{ext}"
        ok = download_logo(url, out)
        if ok:
            downloaded += 1
            print(f"OK  : {name} → {out.relative_to(ROOT)}")
        else:
            print(f"FAIL: {name} → {url}")

    print(f"\nSummary: {downloaded} logos downloaded into {OPP_DIR.relative_to(ROOT)}")
    print("(Report lists any opponents that lacked URLs.)")
    return 0

if __name__ == "__main__":
    sys.exit(main())

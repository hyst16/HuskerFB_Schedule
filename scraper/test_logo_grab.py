# -*- coding: utf-8 -*-
"""
Probe logos from https://huskers.com/sports/football/schedule

- Saves raw HTML snapshot to data/schedule_raw.html
- Prints diagnostics: counts of cards, images, etc.
- Extracts opponent names & best-guess logo URLs from multiple sources:
  * <img> data-src, data-srcset, srcset, src
  * <picture><source srcset>
- Writes detailed report to data/opponent_logos_found.json
- Optionally downloads fetched logos to docs/assets/opponents/_fetched/
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
    # Heavier browser-y headers to avoid stripped markup
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def first_from_srcset(s: str | None) -> str | None:
    if not s:
        return None
    # "url 1x, url2 2x" → take first URL
    return s.split(",")[0].strip().split(" ")[0]

def is_placeholder(u: str | None) -> bool:
    return not u or u.startswith("data:image")

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")

def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def get_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def extract_from_picture(pic) -> str | None:
    # <picture><source srcset="..."> ... <img ...></picture>
    # Try sources first
    for source in pic.find_all("source"):
        u = first_from_srcset(source.get("data-srcset")) or first_from_srcset(source.get("srcset"))
        if u and not is_placeholder(u):
            return u
    # Then the fallback img
    img = pic.find("img")
    if img:
        for attr in ("data-src",):
            u = img.get(attr)
            if u and not is_placeholder(u):
                return u
        u = first_from_srcset(img.get("data-srcset")) or first_from_srcset(img.get("srcset"))
        if u and not is_placeholder(u):
            return u
        u = img.get("src")
        if u and not is_placeholder(u):
            return u
    return None

def extract_from_img(img) -> str | None:
    for attr in ("data-src",):
        u = img.get(attr)
        if u and not is_placeholder(u):
            return u
    u = first_from_srcset(img.get("data-srcset")) or first_from_srcset(img.get("srcset"))
    if u and not is_placeholder(u):
        return u
    u = img.get("src")
    if u and not is_placeholder(u):
        return u
    return None

def probe() -> list[dict]:
    html = get_html(URL)
    # Save snapshot for manual inspection
    (DATA / "schedule_raw.html").write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, "lxml")

    # Cards that typically include the logos/opponents
    cards = soup.select("div.schedule-event-item-default")
    # Fallback containers if class names differ:
    if not cards:
        cards = soup.select("div.schedule-event-item") or soup.select("li.schedule__list-item")

    print(f"Cards found: {len(cards)}")

    results = []
    for idx, card in enumerate(cards, start=1):
        # Opponent name
        on_el = card.select_one(".schedule-event-item-default__opponent-name") or \
                card.select_one(".opponent, .team")
        opp_name = clean(on_el.get_text()) if on_el else None
        opp_slug = slugify(opp_name) if opp_name else None

        # Prefer the images wrapper used by WMT
        imgs_block = card.select(".schedule-event-item-default__images")
        imgs = []
        if imgs_block:
            imgs = imgs_block[0].find_all("img")
            # Also consider a <picture> wrapper if present
            pics = imgs_block[0].find_all("picture")
        else:
            imgs = card.find_all("img")
            pics = card.find_all("picture")

        # Try picture sources first (often where real srcset lives)
        logo_url = None
        for pic in pics:
            cand = extract_from_picture(pic)
            # Heuristic: opponent is usually NOT the Nebraska N; skip if alt contains 'nebraska'
            if cand:
                # If picture has an <img alt>, filter on alt
                img_fallback = pic.find("img")
                alt_ok = True
                if img_fallback and opp_name:
                    alt_txt = (img_fallback.get("alt") or "").lower()
                    if "nebraska" in alt_txt:
                        alt_ok = False
                if alt_ok:
                    logo_url = cand
                    break

        # If not found via <picture>, fall back to last <img> in the images block
        if not logo_url:
            if imgs:
                opp_img = imgs[-1]  # typically [Nebraska, Opponent]
                logo_url = extract_from_img(opp_img)

        # Fallback: any image in the card whose alt matches the opponent (loose)
        if not logo_url and opp_name:
            for im in card.select("img[alt]"):
                alt = clean(im.get("alt"))
                if not alt:
                    continue
                if "nebraska" in alt.lower():
                    continue
                a = slugify(alt)
                if a == opp_slug or (opp_slug and (opp_slug in a or a in opp_slug)):
                    logo_url = extract_from_img(im)
                    if logo_url:
                        break

        # Minimal per-card diagnostics
        results.append({
            "card_index": idx,
            "opponent_name": opp_name,
            "opponent_slug": opp_slug,
            "images_in_block": len(imgs),
            "pictures_in_block": len(pics),
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
    if ext in (".svg", ".png", ".jpg", ".jpeg", ".webp"):
        return ext
    return ".svg"

def main() -> int:
    rows = probe()

    # Write detailed report
    report_path = DATA / "opponent_logos_found.json"
    report_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote report: {report_path.relative_to(ROOT)}")
    print(f"Snapshot saved: { (DATA/'schedule_raw.html').relative_to(ROOT) }")
    print(f"First 3 rows (preview):")
    for r in rows[:3]:
        print(json.dumps(r, indent=2))

    # Attempt downloads for found logos
    downloaded = 0
    for row in rows:
        url = row.get("logo_url")
        slug = row.get("opponent_slug")
        name = row.get("opponent_name")
        if not (url and slug):
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
    return 0

if __name__ == "__main__":
    sys.exit(main())

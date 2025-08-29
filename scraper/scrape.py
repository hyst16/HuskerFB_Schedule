# -*- coding: utf-8 -*-
"""
Scrapes https://huskers.com/sports/football/schedule (Sidearm layout)
Writes:
  data/schedule.json
  data/stadiums_needed.json
  data/stadiums_missing.json
Also copies those into docs/ for the Pages site.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from scraper.utils import slugify, normalize_tv

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
ASSETS_STADIUMS = ROOT / "assets" / "stadiums"
DATA.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)
ASSETS_STADIUMS.mkdir(parents=True, exist_ok=True)

SCHEDULE_URL = "https://huskers.com/sports/football/schedule"

# Optional alias mapping for venue names → desired slug
ALIASES = {}
aliases_csv = ASSETS_STADIUMS / "aliases.csv"
if aliases_csv.exists():
    for line in aliases_csv.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "," not in line:
            continue
        src, slug = [x.strip() for x in line.split(",", 1)]
        if src and slug:
            ALIASES[src] = slug


def get_html(url: str) -> str:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def parse_schedule(html: str):
    soup = BeautifulSoup(html, "lxml")

    # Try a few common selectors Sidearm uses
    rows = []
    for sel in [
        ".sidearm-schedule-game",
        "li.schedule__list-item",
        "div.schedule_game",
        "tr",
    ]:
        rows = soup.select(sel)
        if rows:
            break

    games = []
    for r in rows:
        txt_all = r.get_text(" ", strip=True)

        # DATE
        date_str = None
        date_el = r.select_one("[data-date]") or r.select_one(
            ".sidearm-schedule-game-opponent-date"
        )
        if date_el and date_el.get("data-date"):
            date_str = date_el["data-date"]
        else:
            m = re.search(
                r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}",
                txt_all,
                re.I,
            )
            date_str = m.group(0) if m else None

        # TIME
        time_str = None
        t_el = r.select_one("[data-time]") or r.select_one(
            ".sidearm-schedule-game-opponent-time"
        )
        if t_el and t_el.get("data-time"):
            time_str = t_el["data-time"]
        else:
            m = re.search(r"(\d{1,2}:\d{2}\s*[ap]m|tba)", txt_all, re.I)
            time_str = m.group(0) if m else None

        # SITE
        site = "home"
        if re.search(r"\bat\b", txt_all, re.I):
            site = "away"
        if re.search(r"neutral", txt_all, re.I):
            site = "neutral"

        # OPPONENT
        opp = None
        opp_el = r.select_one(
            ".sidearm-schedule-game-opponent-name, .opponent, .team, .sidearm-schedule-game-opponent-text"
        )
        if opp_el:
            opp = opp_el.get_text(" ", strip=True)
        else:
            m = re.search(r"\b(vs\.|at)\s+([^\n\r]+?)(?:\s{2,}|$)", txt_all, re.I)
            opp = m.group(2).strip() if m else None

        # LOCATION
        city, venue = None, None
        loc_el = r.select_one(".sidearm-schedule-game-location, .location")
        if loc_el:
            loc_txt = loc_el.get_text(" ", strip=True)
            if " / " in loc_txt:
                city, venue = [x.strip() for x in loc_txt.split(" / ", 1)]
            else:
                parts = [p.strip() for p in re.split(r"\s{2,}|\|", loc_txt) if p.strip()]
                if len(parts) >= 2:
                    city, venue = parts[0], parts[-1]
                else:
                    city = loc_txt

        # TV
        tv = None
        tv_el = r.select_one(".sidearm-schedule-game-video, .tv, .network")
        if tv_el:
            tv = normalize_tv(tv_el.get_text(" ", strip=True))
        else:
            m = re.search(
                r"\b(fox|fs1|fs2|btn|abc|espn2|espn|espnu|nbc|cbs|peacock)\b", txt_all, re.I
            )
            tv = normalize_tv(m.group(1)) if m else None

        # Build date/time fields
        date_iso = None
        time_local = None
        weekday = None
        tba = False
        if date_str:
            try:
                now = datetime.now()
                m2 = re.search(
                    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})",
                    date_str,
                    re.I,
                )
                if m2:
                    month_str = m2.group(1).title()
                    day = int(m2.group(2))
                    month_map = {
                        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
                    }
                    mm = month_map[month_str]
                    year = now.year
                    if mm < now.month - 1:
                        year = now.year + 1
                    date_obj = datetime(year, mm, day)
                    weekday = date_obj.strftime("%A").upper()
                    if time_str and time_str.lower() != "tba":
                        ts = re.sub(r"\s+", " ", time_str.upper().replace(".", ""))
                        try:
                            date_dt = datetime.strptime(
                                f"{month_str} {day}, {year} {ts}", "%b %d, %Y %I:%M %p"
                            )
                        except ValueError:
                            try:
                                date_dt = datetime.strptime(
                                    f"{month_str} {day}, {year} {ts}",
                                    "%B %d, %Y %I:%M %p",
                                )
                            except ValueError:
                                date_dt = datetime(year, mm, day, 12, 0)
                        date_iso = date_dt.isoformat()
                        time_local = ts
                    else:
                        tba = True
                        date_iso = date_obj.isoformat()
                        time_local = "TBA"
            except Exception:
                pass

        va = "vs." if site == "home" else "at"

        # Stadium slug
        venue_label = venue or ""
        if venue_label in ALIASES:
            venue_slug = ALIASES[venue_label]
        else:
            tag = ""
            if city:
                tag = "-" + slugify(re.sub(r",.*$", "", city))
            base = venue_label or (city or "stadium")
            base_slug = slugify(base)
            venue_slug = base_slug + (tag if tag and base_slug not in tag else "")

        games.append(
            {
                "date_iso": date_iso,
                "weekday": weekday,
                "date_str": date_str,
                "time_local": time_local,
                "tba": tba,
                "site": site,
                "va": va,
                "opponent_name": opp,
                "opponent_slug": slugify(opp) if opp else None,
                "location_city": city,
                "location_venue": venue_label,
                "stadium_slug": venue_slug,
                "tv_network": tv,
                "status": "scheduled",
            }
        )

    # Filter obviously empty rows
    games = [g for g in games if g.get("opponent_name")]
    return games


def write_json(path: Path, obj) -> bool:
    old = None
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            old = None
    new_txt = json.dumps(obj, ensure_ascii=False, indent=2)
    if old is None or json.dumps(old, ensure_ascii=False, indent=2) != new_txt:
        path.write_text(new_txt + "\n", encoding="utf-8")
        return True
    return False


def main():
    html = get_html(SCHEDULE_URL)
    games = parse_schedule(html)

    # Sort by date if possible
    def sort_key(g):
        di = g.get("date_iso")
        return di or f"zzz-{g.get('opponent_name','')}"
    games.sort(key=sort_key)

    changed = write_json(DATA / "schedule.json", games)

    # Stadium needs (unique slugs)
    slugs = sorted({g["stadium_slug"] for g in games if g.get("stadium_slug")})
    write_json(DATA / "stadiums_needed.json", slugs)

    # Missing images vs /assets/stadiums/*.jpg
    missing = [slug for slug in slugs if not (ASSETS_STADIUMS / f"{slug}.jpg").exists()]
    write_json(DATA / "stadiums_missing.json", missing)

    # Copy JSON into docs/ so site can fetch
    for f in ["schedule.json", "stadiums_needed.json", "stadiums_missing.json"]:
        src = DATA / f
        dst = DOCS / f
        if src.exists():
            txt = src.read_text(encoding="utf-8")
            if not dst.exists() or dst.read_text(encoding="utf-8") != txt:
                dst.write_text(txt, encoding="utf-8")

    print(
        f"Scraped {len(games)} games. Stadium images missing: {len(missing)} → {missing}"
    )


if __name__ == "__main__":
    sys.exit(main())

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

    games = []

    # 1) Try WMT "table" view first: headers like Date / Teams / Location / Time/Results
    target_table = None
    for table in soup.find_all("table"):
        # gather header text
        heads = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if not heads:
            # some WMT tables use thead/tbody; try thead only
            thead = table.find("thead")
            if thead:
                heads = [th.get_text(" ", strip=True).lower() for th in thead.find_all("th")]
        if any("date" in h for h in heads) and any("location" in h for h in heads):
            target_table = table
            break

    def clean(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())

    def parse_date_tokens(date_txt: str):
        # Example: "Thursday Aug 28"
        m = re.search(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\s+([A-Z][a-z]{2,})\s+(\d{1,2})", date_txt, re.I)
        if not m:
            # Sometimes they render as "Saturday Sep 6"
            m = re.search(r"([A-Z][a-z]{2,})\s+(\d{1,2})", date_txt, re.I)
            if not m:
                return None, None, None, None
            weekday = None
            month_str, day = m.group(1).title(), int(m.group(2))
        else:
            weekday = m.group(1).upper()
            month_str, day = m.group(2).title(), int(m.group(3))

        month_map = {
            "Jan":1,"January":1,"Feb":2,"February":2,"Mar":3,"March":3,"Apr":4,"April":4,
            "May":5,"Jun":6,"June":6,"Jul":7,"July":7,"Aug":8,"August":8,"Sep":9,"Sept":9,"September":9,
            "Oct":10,"October":10,"Nov":11,"November":11,"Dec":12,"December":12
        }
        mm = month_map.get(month_str, None)
        if not mm:
            return None, None, None, None
        now = datetime.now()
        year = now.year
        if mm < now.month - 1:
            year = now.year + 1
        return weekday, month_str[:3], day, year

    def determine_site(va_txt: str, city: str | None) -> str:
        va_txt = (va_txt or "").lower()
        city = (city or "").lower()
        if "at" in va_txt:
            return "away"
        # "vs." can be home or neutral; Lincoln is home, otherwise treat as neutral
        if "lincoln" in city:
            return "home"
        return "neutral"

    if target_table:
        # Parse table rows
        tbody = target_table.find("tbody") or target_table
        for tr in tbody.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) < 4:
                continue

            date_col = clean(tds[0].get_text(" ", strip=True))
            teams_col = clean(tds[1].get_text("\n", strip=True))
            loc_col = clean(tds[2].get_text(" ", strip=True))
            time_col = clean(tds[3].get_text(" ", strip=True))

            # Teams column looks like:
            # "vs.\nCincinnati" or "at\nMaryland"
            va = "vs."
            opp_name = teams_col
            mteams = re.search(r"^(vs\.|at)\s*(.*)$", teams_col, re.I | re.M)
            if mteams:
                va = mteams.group(1).lower()
                opp_name = mteams.group(2).strip()

            # Location column usually: "Kansas City, Mo. / Arrowhead Stadium"
            city, venue = None, None
            if " / " in loc_col:
                city, venue = [x.strip() for x in loc_col.split(" / ", 1)]
            else:
                # sometimes it repeats city twice; take first token
                parts = [p.strip() for p in re.split(r"\s{2,}|\|", loc_col) if p.strip()]
                if parts:
                    city = parts[0]

            # Time
            tv = None
            tba = False
            time_local = None
            if not time_col or time_col.upper() == "TBA":
                tba = True
                time_local = "TBA"
            else:
                # Time/Results may contain result strings; keep only a time like "6:30 PM CDT" / "11:00 AM CST"
                mt = re.search(r"\b(\d{1,2}:\d{2}\s*[AP]M(?:\s*[A-Z]{2,3}T)?)\b", time_col, re.I)
                if mt:
                    time_local = mt.group(1).upper().replace(".", "")
                else:
                    tba = True
                    time_local = "TBA"

            # Parse date
            weekday, mo3, day, year = parse_date_tokens(date_col)
            date_iso = None
            date_str = None
            if mo3 and day and year:
                date_str = f"{mo3} {day}"
                if not tba and time_local:
                    # Build a datetime with time if we have it
                    # Strip timezone text for ISO—display stays as-is
                    mt2 = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)", time_local, re.I)
                    if mt2:
                        hh = int(mt2.group(1))
                        mm = int(mt2.group(2))
                        ampm = mt2.group(3).upper()
                        if ampm == "PM" and hh != 12:
                            hh += 12
                        if ampm == "AM" and hh == 12:
                            hh = 0
                        date_iso = datetime(year, {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}[mo3], day, hh, mm).isoformat()
                    else:
                        date_iso = datetime(year, {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}[mo3], day).isoformat()
                else:
                    date_iso = datetime(year, {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}[mo3], day).isoformat()

            site = determine_site(va, city)
            opp_slug = slugify(opp_name) if opp_name else None

            # Stadium slug (use alias if provided)
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

            games.append({
                "date_iso": date_iso,
                "weekday": weekday,
                "date_str": date_str or date_col,
                "time_local": time_local,
                "tba": tba,
                "site": site,
                "va": va,
                "opponent_name": opp_name,
                "opponent_slug": opp_slug,
                "location_city": city,
                "location_venue": venue_label,
                "stadium_slug": venue_slug,
                "tv_network": tv,  # (WMT doesn't always list TV in the table; we keep null/TBA)
                "status": "scheduled",
            })

    # 2) If table not found (future-proof), fall back to your previous block parser
    if not games:
        # (keep your existing non-table parsing here if you want a fallback)
        pass

    # --- Enrichment pass using WMT card markup ---
    # Build a lookup from opponent name → details found in cards
    card_info = []

    # Each card has opponent name/logo, vs./at, location and a bottom list that can include a TV logo
    for card in soup.select("div.schedule-event-item-default"):
        # Opponent name
        on_el = card.select_one(".schedule-event-item-default__opponent-name")
        opp_name_clean = on_el.get_text(strip=True) if on_el else None

        # vs/at
        va_el = card.select_one(".schedule-event-item-default__divider")
        va_txt = va_el.get_text(strip=True).lower() if va_el else None
        if va_txt not in ("vs.", "at"):
            va_txt = "vs."
          
         # Opponent logo (2nd image under __images is opponent)
        logo_url = None
        imgs = card.select(".schedule-event-item-default__images img")
        if imgs and len(imgs) >= 2:
            cand = imgs[-1]
        
            # helper to pull first url from a srcset-like string
            def first_from_srcset(s: str | None) -> str | None:
                if not s: return None
                return s.split(",")[0].strip().split(" ")[0]
        
            # Prefer data-* sources (lazy-loaded), then srcset, finally src
            url_order = [
                cand.get("data-src"),
                first_from_srcset(cand.get("data-srcset")),
                first_from_srcset(cand.get("srcset")),
                cand.get("src"),
            ]
            for u in url_order:
                if u and not u.startswith("data:image"):
                    logo_url = u
                    break
                  
        # Location "City, ST / Venue"
        loc_el = card.select_one(".schedule-event-location")
        loc_txt = loc_el.get_text(" ", strip=True) if loc_el else None
        city, venue = None, None
        if loc_txt:
            if " / " in loc_txt:
                city, venue = [x.strip() for x in loc_txt.split(" / ", 1)]
            else:
                city = loc_txt

        # TV: image alt inside the bottom link list
        tv_alt = None
        tv_img = card.find_next("div", class_="schedule-event-bottom__list")
        if tv_img:
            img = tv_img.select_one("a.schedule-event-bottom__link img[alt]")
            if img:
                tv_alt = (img.get("alt") or "").strip()

        card_info.append({
            "opp_name": opp_name_clean,
            "va": va_txt,
            "city": city,
            "venue": venue,
            "logo": logo_url,
            "tv_alt": tv_alt,
        })

    # Normalize TV names
    def tv_norm(tv_alt):
        if not tv_alt:
            return None
        key = re.sub(r"[^a-z0-9 ]+", "", tv_alt.lower().strip())
        # our utils.normalize_tv handles "big ten network" -> 'btn'
        from scraper.utils import normalize_tv
        return normalize_tv(key) or normalize_tv(tv_alt)

    # Merge card info into games by opponent name (best-effort)
    for g in games:
        name = (g.get("opponent_name") or "").strip()
        # if table parser produced junk, prefer a card match on contains
        best = None
        for ci in card_info:
            if not ci["opp_name"]:
                continue
            # loose match: either side contains the other (casefold)
            a, b = ci["opp_name"].casefold(), name.casefold()
            if a and (a in b or b in a):
                best = ci
                break
        if best:
            g["opponent_name"] = best["opp_name"] or g["opponent_name"]
            g["opponent_slug"] = slugify(best["opp_name"]) if best["opp_name"] else g.get("opponent_slug")
            g["va"] = best["va"] or g.get("va")
            if best["city"]:
                g["location_city"] = best["city"]
            if best["venue"]:
                g["location_venue"] = best["venue"]
                # recompute stadium slug with city tag
                tag = "-" + slugify(re.sub(r",.*$", "", best["city"])) if best["city"] else ""
                base = best["venue"]
                base_slug = slugify(base)
                g["stadium_slug"] = base_slug + (tag if tag and base_slug not in tag else "")
            g["opponent_logo_url"] = best["logo"]
            g["tv_network"] = tv_norm(best["tv_alt"]) or g.get("tv_network")

    # Filter empties
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

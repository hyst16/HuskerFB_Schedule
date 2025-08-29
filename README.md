# Nebraska Football — TV Schedule (PosterBooking-ready)


Two views auto-cycling on one URL:
1. **Hero (Next Game)** — full-bleed stadium photo + opponent lockup, date/time/location, TV logo.
2. **Full Season** — entire schedule on one screen (auto 2‑column only if overflow).


## How it works
- A GitHub Action scrapes the schedule from huskers.com and writes:
- `data/schedule.json`
- `data/stadiums_needed.json` (unique stadium slugs required)
- `data/stadiums_missing.json` (which files you still need to add)
- The same run copies those JSONs into `docs/` for the Pages site.
- Point PosterBooking at your Pages URL (this repo → Settings → Pages → Source: `main` / `docs/`).


## Stadium images (you add)
Put your JPGs here:

assets/stadiums/.jpg


**Slug format:** `<venue-name>-<city-or-unique>.jpg` (lowercase; hyphens). Examples:
- Memorial Stadium (Lincoln, Neb.) → `memorial-stadium-lincoln.jpg`
- GEHA Field at Arrowhead Stadium → `arrowhead-stadium-kansas-city.jpg`
- Michigan Stadium → `michigan-stadium-ann-arbor.jpg`


**Optional alias map:** `assets/stadiums/aliases.csv`

source_venue,slug GEHA Field at Arrowhead Stadium,arrowhead-stadium-kansas-city Memorial Stadium (Lincoln, Neb.),memorial-stadium-lincoln

## Configure cycle time
Append `?cycle=15` to the URL to use a 15s cycle per view (default 12s).


## Local dev
```bash
python -m venv .venv && source .venv/bin/activate
pip install requests beautifulsoup4 lxml
python scraper/scrape.py
python -m http.server --directory docs 8080
# open http://localhost:8080


Notes

The scraper is resilient to minor HTML changes but may need selector tweaks if the site revamps.

Times display in CDT/CST text as scraped/parsed. TBA renders clean.

Past games can be dimmed later by updating status if you decide to track finals.


---


## What you need to add right now
1) **Pages source:** set to `main` → `/docs` in repo settings.
2) **Add at least one fallback:** `assets/stadiums/memorial-stadium-lincoln.jpg`.
3) (Optional) Drop TV SVGs into `docs/tv/`:
- `n-logo.svg`, `opponent.svg`
- `fox.svg`, `fs1.svg`, `fs2.svg`, `btn.svg`, `cbs.svg`, `nbc.svg`, `peacock.svg`, `abc.svg`, `espn.svg`, `espn2.svg`, `espnu.svg`
4) Push to GitHub; the Action will populate JSON and the checklist.


---


**Done.** After you push, open:
- TV page: `/docs/index.html`
- Stadium checklist: `/docs/checklist.html`



# -*- coding: utf-8 -*-
'site': site,
'va': va,
'opponent_name': opp,
'opponent_slug': slugify(opp) if opp else None,
'location_city': city,
'location_venue': venue_label,
'stadium_slug': venue_slug,
'tv_network': tv,
'status': 'scheduled'
})


# Filter obviously empty rows
games = [g for g in games if g.get('opponent_name')]
return games




def write_json(path: Path, obj) -> bool:
old = None
if path.exists():
try:
old = json.loads(path.read_text(encoding='utf-8'))
except Exception:
old = None
new_txt = json.dumps(obj, ensure_ascii=False, indent=2)
if old is None or json.dumps(old, ensure_ascii=False, indent=2) != new_txt:
path.write_text(new_txt + "\n", encoding='utf-8')
return True
return False




def main():
html = get_html(SCHEDULE_URL)
games = parse_schedule(html)


# Sort by date if possible
def sort_key(g):
di = g.get('date_iso')
return di or f"zzz-{g.get('opponent_name','') }"
games.sort(key=sort_key)


changed = write_json(DATA / 'schedule.json', games)


# Stadium needs (unique slugs)
slugs = sorted({g['stadium_slug'] for g in games if g.get('stadium_slug')})
write_json(DATA / 'stadiums_needed.json', slugs)


# Missing images vs /assets/stadiums/*.jpg
missing = []
for slug in slugs:
if not (ASSETS_STADIUMS / f"{slug}.jpg").exists():
missing.append(slug)
write_json(DATA / 'stadiums_missing.json', missing)


# Copy JSON into docs/ so site can fetch without CORS/path issues
DOCS.mkdir(parents=True, exist_ok=True)
for f in ['schedule.json', 'stadiums_needed.json', 'stadiums_missing.json']:
src = DATA / f
dst = DOCS / f
if src.exists():
txt = src.read_text(encoding='utf-8')
if not dst.exists() or dst.read_text(encoding='utf-8') != txt:
dst.write_text(txt, encoding='utf-8')


print(f"Scraped {len(games)} games. Stadium images missing: {len(missing)} → {missing}")


if __name__ == '__main__':
sys.exit(main())

# -*- coding: utf-8 -*-
import re
from datetime import datetime
from zoneinfo import ZoneInfo


TV_MAP = {
'big ten network': 'btn', 'btn': 'btn',
'fox': 'fox', 'fs1': 'fs1', 'fs2': 'fs2',
'cbs': 'cbs', 'nbc': 'nbc', 'peacock': 'peacock',
'abc': 'abc', 'espn': 'espn', 'espn2': 'espn2', 'espnu': 'espnu'
}


CHICAGO_TZ = ZoneInfo('America/Chicago')


_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(s: str) -> str:
s = s.lower().strip()
s = _slug_re.sub('-', s)
s = re.sub(r'-+', '-', s).strip('-')
return s


def normalize_tv(s: str | None) -> str | None:
if not s:
return None
key = s.lower().strip()
key = re.sub(r"[^a-z0-9 ]+", "", key)
return TV_MAP.get(key, None)


def to_chicago_time(dt: datetime) -> datetime:
# If dt is naive (no tz), assume it's already local; else convert
if dt.tzinfo is None:
return dt.replace(tzinfo=CHICAGO_TZ)
return dt.astimezone(CHICAGO_TZ)

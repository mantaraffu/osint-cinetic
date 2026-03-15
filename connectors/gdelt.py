import csv
import io
import zipfile
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

from .base import OsintConnector, NormalizedEvent

GDELT_LASTUPDATE = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

COL = {
    "GLOBALEVENTID":        0,
    "SQLDATE":              1,
    "Actor1Type1Code":     14,
    "Actor1Type2Code":     15,
    "Actor2Type1Code":     23,
    "Actor2Type2Code":     24,
    "EventCode":           26,
    "EventRootCode":       28,
    "Actor1Geo_FullName":  36,
    "Actor1Geo_Lat":       40,
    "Actor1Geo_Long":      41,
    "ActionGeo_Type":      51,
    "ActionGeo_FullName":  52,
    "ActionGeo_Lat":       56,
    "ActionGeo_Long":      57,
    "SOURCEURL":           60,
}

MILITARY_EVENT_CODES = {"190", "191", "192", "193", "194", "195", "196"}
MILITARY_ACTOR_TYPES = {"MIL", "REB", "GOV", "SPY", "UAF", "MOV"}
EXCLUDE_URL_KEYWORDS  = ["police", "gang", "murder", "crime", "drug", "theft", "arrest"]

CAMEO_TYPE = {
    "190": "military_force",
    "191": "blockade",
    "192": "occupation",
    "193": "small_arms",
    "194": "artillery_armor",
    "195": "airstrike",
    "196": "ceasefire_violation",
}


def _build_url(dt: datetime) -> str:
    minute = (dt.minute // 15) * 15
    rounded = dt.replace(minute=minute, second=0, microsecond=0)
    return f"http://data.gdeltproject.org/gdeltv2/{rounded.strftime('%Y%m%d%H%M%S')}.export.CSV.zip"


def _score_row(row: list) -> int:
    score = 0
    if row[COL["EventCode"]] in {"193", "194", "195", "196"}:
        score += 3
    elif row[COL["EventCode"]] in {"191", "192"}:
        score += 2
    for c in [COL["Actor1Type1Code"], COL["Actor1Type2Code"],
              COL["Actor2Type1Code"], COL["Actor2Type2Code"]]:
        if c < len(row) and row[c] in MILITARY_ACTOR_TYPES:
            score += 2
            break
    url = row[COL["SOURCEURL"]].lower() if len(row) > 60 else ""
    for kw in ["war", "attack", "strike", "military", "troops", "missile", "drone", "combat"]:
        if kw in url:
            score += 1
            break
    for kw in EXCLUDE_URL_KEYWORDS:
        if kw in url:
            score -= 3
            break
    return score


def _row_to_event(row: list) -> Optional[NormalizedEvent]:
    try:
        ts = datetime.strptime(row[COL["SQLDATE"]], "%Y%m%d").replace(
            tzinfo=timezone.utc
        ).isoformat()
    except (ValueError, IndexError):
        ts = datetime.now(timezone.utc).isoformat()

    def safe_float(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    lat = safe_float(row[COL["ActionGeo_Lat"]])
    lng = safe_float(row[COL["ActionGeo_Long"]])
    if lat == 0.0 and lng == 0.0:
        return None

    location   = row[COL["ActionGeo_FullName"]] or row[COL["Actor1Geo_FullName"]] or "Unknown"
    event_code = row[COL["EventCode"]]
    source_url = row[COL["SOURCEURL"]]
    event_id   = row[COL["GLOBALEVENTID"]]

    return NormalizedEvent(
        timestamp=ts,
        location_name=location,
        lat=lat,
        lng=lng,
        event_type=CAMEO_TYPE.get(event_code, "military_action"),
        description=f"CAMEO {event_code} — {CAMEO_TYPE.get(event_code, 'military action')} in {location}",
        source="GDELT 2.0",
        source_url=source_url,
        raw={"id": event_id, "event_code": event_code},
    )


class GdeltConnector(OsintConnector):

    id = "gdelt"
    name = "GDELT 2.0 Events DB"
    frequency_minutes = 15

    def _candidate_urls(self) -> list:
        urls = []
        try:
            resp = requests.get(GDELT_LASTUPDATE, timeout=10)
            resp.raise_for_status()
            for line in resp.text.strip().splitlines():
                parts = line.strip().split(" ")
                if len(parts) == 3 and parts[2].endswith(".export.CSV.zip"):
                    urls.append(parts[2])
                    break
        except Exception as e:
            print(f"[gdelt] lastupdate.txt non disponibile: {e}")

        now = datetime.now(timezone.utc)
        for i in range(8):
            urls.append(_build_url(now - timedelta(minutes=15 * i)))

        seen = set()
        result = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result

    def _download_csv(self) -> Optional[str]:
        for url in self._candidate_urls():
            print(f"[gdelt] Provo {url}")
            try:
                r = requests.get(url, timeout=30)
                if r.status_code == 200:
                    print("[gdelt] OK")
                    zf = zipfile.ZipFile(io.BytesIO(r.content))
                    return zf.read(zf.namelist()[0]).decode("utf-8")
                print(f"[gdelt] {r.status_code}, provo slot precedente...")
            except Exception as e:
                print(f"[gdelt] Errore: {e}")
        return None

    def _filter_rows(self, csv_content: str) -> list:
        candidates = []
        reader = csv.reader(io.StringIO(csv_content), delimiter="\t")
        for row in reader:
            if len(row) <= 60:
                continue
            if row[COL["EventRootCode"]] != "19":
                continue
            if row[COL["EventCode"]] not in MILITARY_EVENT_CODES:
                continue
            try:
                geo_type = int(row[COL["ActionGeo_Type"]])
            except (ValueError, TypeError):
                geo_type = 0
            if geo_type < 3:
                continue
            candidates.append(row)
        candidates.sort(key=lambda r: (_score_row(r), r[COL["SQLDATE"]]), reverse=True)
        return candidates

    def fetch_latest(self) -> Optional[NormalizedEvent]:
        csv_content = self._download_csv()
        if not csv_content:
            return None
        rows = self._filter_rows(csv_content)
        if not rows:
            print("[gdelt] Nessun evento militare qualificato trovato")
            return None
        print(f"[gdelt] {len(rows)} eventi candidati, seleziono il più rilevante")
        return _row_to_event(rows[0])

    def fetch_all(self) -> list:
        csv_content = self._download_csv()
        if not csv_content:
            return []
        rows = self._filter_rows(csv_content)
        if not rows:
            return []
        print(f"[gdelt] {len(rows)} eventi militari qualificati trovati")
        events = []
        for row in rows[:50]:
            ev = _row_to_event(row)
            if ev:
                events.append(ev)
        return events

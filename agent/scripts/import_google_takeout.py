#!/usr/bin/env python3
"""
Google Takeout → InfluxDB importer.

Imports: Google Fit daily activity, Chrome history, Calendar, Maps saved places.
"""
import csv
import glob
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from home_iot.config import settings

log = logging.getLogger(__name__)
SEOUL = timezone(timedelta(hours=9))


def _get_client():
    client = InfluxDBClient(url=settings.influx_url, token=settings.influx_token, org=settings.influx_org)
    return client, client.write_api(write_options=SYNCHRONOUS)


def _write_batch(write_api, points, label=""):
    for i in range(0, len(points), 5000):
        write_api.write(bucket=settings.influx_bucket, record=points[i:i+5000])
    if points:
        log.info(f"  {label}: {len(points)} points")


# ============================================================
# 1. Google Fit Daily Activity (15-min interval CSVs)
# ============================================================

COL_MAP = {
    "칼로리(kcal)": "calories",
    "거리(m)": "distance_m",
    "걸음 수": "steps",
    "평균 심박수(bpm)": "hr_avg",
    "최대 심박수(bpm)": "hr_max",
    "최소 심박수(bpm)": "hr_min",
    "평균 속도(m/s)": "speed_avg",
    "비활동 기간(ms)": "inactive_ms",
    "걷기 기간(ms)": "walking_ms",
    "달리기 기간(ms)": "running_ms",
    "고강도 활동 시간(분)": "high_intensity_min",
    "심장 강화 점수": "cardio_score",
    "평균 몸무게(kg)": "weight_avg",
}


def import_fit_daily(takeout_dir: Path) -> int:
    fit_dir = takeout_dir / "피트니스" / "일일 활동 측정항목"
    if not fit_dir.exists():
        log.warning("Google Fit daily dir not found")
        return 0

    files = sorted(fit_dir.glob("2*.csv"))
    log.info(f"Google Fit daily: {len(files)} files")

    client, write_api = _get_client()
    total = 0

    for fpath in files:
        date_str = fpath.stem  # e.g. "2024-01-15"
        try:
            base_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=SEOUL)
        except ValueError:
            continue

        points = []
        with open(fpath, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Parse time from "HH:MM:SS.sss+09:00"
                start_str = row.get("시작 시간", "")
                if not start_str:
                    continue
                try:
                    h, m = int(start_str[:2]), int(start_str[3:5])
                    ts = base_date.replace(hour=h, minute=m, second=0)
                except (ValueError, IndexError):
                    continue

                p = Point("gfit_daily").tag("source", "google_fit")
                has_field = False
                for kor, eng in COL_MAP.items():
                    val = row.get(kor, "").strip()
                    if val:
                        try:
                            p = p.field(eng, float(val))
                            has_field = True
                        except ValueError:
                            pass
                if has_field:
                    p = p.time(ts.astimezone(timezone.utc))
                    points.append(p)

        if points:
            _write_batch(write_api, points)
            total += len(points)

    client.close()
    log.info(f"Google Fit daily total: {total} points")
    return total


# ============================================================
# 2. Google Fit Sessions (Sleep, Exercise)
# ============================================================

def import_fit_sessions(takeout_dir: Path) -> int:
    sess_dir = takeout_dir / "피트니스" / "모든 세션"
    if not sess_dir.exists():
        return 0

    files = sorted(sess_dir.glob("*.json"))
    log.info(f"Google Fit sessions: {len(files)} files")

    client, write_api = _get_client()
    points = []

    for fpath in files:
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except:
            continue

        # Filename pattern: 2016-03-29T02_24_50.532+09_00_SLEEP.json
        name = fpath.stem
        parts = name.rsplit("_", 1)
        activity_type = parts[-1] if len(parts) > 1 else "UNKNOWN"

        start_ms = data.get("startTimeMillis")
        end_ms = data.get("endTimeMillis")
        if not start_ms:
            continue

        ts = datetime.fromtimestamp(int(start_ms) / 1000, tz=timezone.utc)
        p = Point("gfit_session").tag("source", "google_fit").tag("activity", activity_type)

        if end_ms:
            duration_min = (int(end_ms) - int(start_ms)) / 60000
            p = p.field("duration_min", duration_min)

        # Extract aggregate stats if available
        for seg in data.get("aggregate", []):
            for dp in seg.get("dataPoint", []):
                for fv in dp.get("fitValue", []):
                    val = fv.get("value", {})
                    if "fpVal" in val:
                        field_name = dp.get("dataTypeName", "unknown").split(".")[-1]
                        p = p.field(field_name, float(val["fpVal"]))
                    elif "intVal" in val:
                        field_name = dp.get("dataTypeName", "unknown").split(".")[-1]
                        p = p.field(field_name, int(val["intVal"]))

        p = p.field("marker", 1)  # ensure at least one field
        p = p.time(ts)
        points.append(p)

    _write_batch(write_api, points, "sessions")
    client.close()
    return len(points)


# ============================================================
# 3. Chrome History
# ============================================================

def import_chrome_history(takeout_dir: Path) -> int:
    hist_file = takeout_dir / "Chrome" / "기록.json"
    if not hist_file.exists():
        log.warning("Chrome history not found")
        return 0

    with open(hist_file, encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("Browser History", [])
    log.info(f"Chrome history: {len(entries)} entries")

    client, write_api = _get_client()
    points = []

    for entry in entries:
        time_usec = entry.get("time_usec")
        if not time_usec:
            continue
        ts = datetime.fromtimestamp(int(time_usec) / 1_000_000, tz=timezone.utc)
        url = entry.get("url", "")
        title = entry.get("title", "")

        # Extract domain
        from urllib.parse import urlparse
        try:
            domain = urlparse(url).netloc
            if domain.startswith("www."):
                domain = domain[4:]
        except:
            domain = "unknown"

        p = (Point("chrome_history")
             .tag("source", "google_takeout")
             .tag("domain", domain[:100])
             .field("title", title[:200])
             .field("url", url[:500])
             .field("visit", 1)
             .time(ts))
        points.append(p)

    _write_batch(write_api, points, "chrome")
    client.close()
    return len(points)


# ============================================================
# 4. Calendar (ICS)
# ============================================================

def import_calendar(takeout_dir: Path) -> int:
    cal_dir = takeout_dir / "캘린더"
    if not cal_dir.exists():
        return 0

    total = 0
    client, write_api = _get_client()

    for ics_file in cal_dir.glob("*.ics"):
        cal_name = ics_file.stem
        points = []
        current_event = {}

        with open(ics_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line == "BEGIN:VEVENT":
                    current_event = {}
                elif line == "END:VEVENT":
                    if "DTSTART" in current_event:
                        ts_str = current_event["DTSTART"]
                        summary = current_event.get("SUMMARY", "")
                        try:
                            # Handle various date formats
                            ts_str_clean = ts_str.split(";")[-1].split(":")[-1] if ":" in ts_str else ts_str
                            for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
                                try:
                                    ts = datetime.strptime(ts_str_clean, fmt).replace(tzinfo=timezone.utc)
                                    break
                                except ValueError:
                                    continue
                            else:
                                continue
                            p = (Point("calendar_event")
                                 .tag("source", "google_calendar")
                                 .tag("calendar", cal_name)
                                 .field("summary", summary[:200])
                                 .field("event", 1)
                                 .time(ts))
                            points.append(p)
                        except:
                            pass
                elif ":" in line:
                    key, _, val = line.partition(":")
                    key = key.split(";")[0]
                    current_event[key] = val

        _write_batch(write_api, points, f"calendar:{cal_name}")
        total += len(points)

    client.close()
    return total


# ============================================================
# 5. Maps Saved Places (zone seed)
# ============================================================

def import_saved_places(takeout_dir: Path) -> int:
    places_file = takeout_dir / "지도(내 장소)" / "저장한 장소.json"
    if not places_file.exists():
        return 0

    with open(places_file, encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", []) if isinstance(data, dict) else data
    log.info(f"Saved places: {len(features)} entries")

    client, write_api = _get_client()
    points = []

    for feat in features:
        props = feat.get("properties", {}) if isinstance(feat, dict) else {}
        geo = feat.get("geometry", {})
        coords = geo.get("coordinates", [])

        name = props.get("Title", props.get("name", "unknown"))
        address = props.get("address", props.get("Address", ""))

        if coords and len(coords) >= 2:
            p = (Point("saved_place")
                 .tag("source", "google_maps")
                 .tag("name", str(name)[:100])
                 .field("latitude", float(coords[1]) if len(coords) > 1 else 0)
                 .field("longitude", float(coords[0]))
                 .field("address", str(address)[:200])
                 .field("marker", 1)
                 .time(datetime.now(timezone.utc)))
            points.append(p)

    _write_batch(write_api, points, "saved_places")
    client.close()
    return len(points)


# ============================================================
# Main
# ============================================================

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    takeout_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/mnt/c/Users/upica/Downloads/Takeout")
    if not takeout_dir.exists():
        print(f"Takeout dir not found: {takeout_dir}")
        sys.exit(1)

    print(f"📦 Importing from: {takeout_dir}\n")

    results = {}
    results["gfit_daily"] = import_fit_daily(takeout_dir)
    results["gfit_sessions"] = import_fit_sessions(takeout_dir)
    results["chrome_history"] = import_chrome_history(takeout_dir)
    results["calendar"] = import_calendar(takeout_dir)
    results["saved_places"] = import_saved_places(takeout_dir)

    print(f"\n{'='*50}")
    print("📊 Import complete:")
    total = 0
    for k, v in results.items():
        print(f"  {k:20} {v:>8} points")
        total += v
    print(f"  {'TOTAL':20} {total:>8} points")


if __name__ == "__main__":
    main()

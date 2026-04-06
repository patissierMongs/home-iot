"""
Samsung Health data export → InfluxDB importer.

Samsung Health exports a ZIP containing multiple CSVs:
  com.samsung.health.heart_rate.*.csv
  com.samsung.health.sleep.*.csv
  com.samsung.health.sleep_stage.*.csv
  com.samsung.health.exercise.*.csv
  com.samsung.health.step_count.*.csv
  com.samsung.health.blood_oxygen.*.csv  (SpO2)
  com.samsung.health.stress.*.csv
  com.samsung.health.floors_climbed.*.csv
  com.samsung.health.body_composition.*.csv
  com.samsung.shealth.tracker.pedometer_day_summary.*.csv
  etc.

Each CSV has a header comment block (lines starting with empty fields or metadata),
then actual column headers, then data rows. The first real header row varies by file.

This importer:
  1. Unzips if needed
  2. Auto-detects CSV types by filename pattern
  3. Parses each with type-specific logic
  4. Writes to InfluxDB as separate measurements (samsung_hr, samsung_sleep, etc.)
"""
from __future__ import annotations

import csv
import glob
import io
import logging
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from ..config import settings

log = logging.getLogger(__name__)

SEOUL = timezone(timedelta(hours=9))


def _parse_ts(s: str) -> datetime | None:
    """Parse Samsung Health timestamp formats."""
    if not s or s == "null":
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=SEOUL)
            return dt
        except ValueError:
            continue
    return None


def _safe_float(s: str | None, default: float | None = None) -> float | None:
    if s is None or s == "" or s == "null":
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _safe_int(s: str | None, default: int | None = None) -> int | None:
    if s is None or s == "" or s == "null":
        return default
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return default


def _find_val(row: dict, *keywords: str) -> str | None:
    """Find the first column value whose key contains ALL given keywords (case-insensitive).
    Samsung Health CSVs use verbose column names like 'com.samsung.health.heart_rate.heart_rate'."""
    for k, v in row.items():
        if k is None:
            continue
        kl = k.lower()
        if all(kw.lower() in kl for kw in keywords):
            return v
    return None


def _find_ts(row: dict) -> datetime | None:
    """Find and parse the best timestamp from a Samsung Health row."""
    for col_hint in ("start_time", "create_time", "update_time"):
        v = _find_val(row, col_hint)
        if v:
            ts = _parse_ts(v)
            if ts:
                return ts
    return None


def _read_samsung_csv(path: Path) -> list[dict[str, str]]:
    """
    Read a Samsung Health CSV.

    Samsung Health CSVs have a consistent format:
      Line 1: metadata (package_name, version_number, another_number)
      Line 2: actual column headers
      Line 3+: data rows

    We skip line 1 and parse from line 2 onward.
    """
    with open(path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()

    if len(lines) < 3:
        return []

    # Line 0 is metadata (e.g. "com.samsung.shealth.stress,6313013,9")
    # Line 1 is the real header
    # Line 2+ is data
    # Some files might have the header on line 0 if there's no metadata prefix;
    # detect by checking if line 0 looks like a Samsung package name
    start = 0
    first_line = lines[0].strip()
    if first_line.startswith("com.samsung") or (first_line.count(",") <= 5 and not any(
        col in first_line for col in ("start_time", "create_time", "update_time", "heart_rate", "stage")
    )):
        start = 1  # skip metadata line

    try:
        reader = csv.DictReader(io.StringIO("".join(lines[start:])))
        return list(reader)
    except Exception as e:
        log.warning("Failed to parse %s: %s", path.name, e)
        return []


# ---------- Type-specific parsers ----------

def _parse_heart_rate(rows: list[dict]) -> list[Point]:
    points = []
    for r in rows:
        ts = _find_ts(r)
        # Direct key lookup first (Samsung's exact column name)
        hr = _safe_float(
            r.get("com.samsung.health.heart_rate.heart_rate")
            or r.get("heart_rate")
        )
        # Fallback: find column ending with ".heart_rate" (not ".create_sh_ver" etc.)
        if hr is None:
            for k, v in r.items():
                if k and k.endswith(".heart_rate"):
                    hr = _safe_float(v)
                    break
        if ts and hr and 20 < hr < 250:
            p = Point("samsung_hr").tag("source", "samsung_health").field("bpm", hr).time(ts.astimezone(timezone.utc))
            hr_min = _safe_float(_find_val(r, "min") or r.get("min"))
            hr_max = _safe_float(_find_val(r, "max") or r.get("max"))
            if hr_min and hr_min > 20:
                p = p.field("bpm_min", hr_min)
            if hr_max and hr_max > 20:
                p = p.field("bpm_max", hr_max)
            points.append(p)
    return points


def _parse_sleep(rows: list[dict]) -> list[Point]:
    points = []
    for r in rows:
        ts = _find_ts(r)
        end_str = _find_val(r, "end_time")
        end = _parse_ts(end_str) if end_str else None
        if not ts:
            continue
        duration_min = None
        if end:
            duration_min = (end - ts).total_seconds() / 60
        p = Point("samsung_sleep").tag("source", "samsung_health")
        if duration_min is not None and duration_min > 0:
            p = p.field("duration_min", duration_min)
        efficiency = _safe_float(_find_val(r, "efficiency") or r.get("efficiency"))
        if efficiency is not None:
            p = p.field("efficiency", efficiency)
        quality = _safe_int(_find_val(r, "quality") or r.get("quality"))
        if quality is not None:
            p = p.field("quality", quality)
        p = p.time(ts.astimezone(timezone.utc))
        points.append(p)
    return points


def _parse_sleep_stage(rows: list[dict]) -> list[Point]:
    points = []
    for r in rows:
        ts = _find_ts(r)
        stage = _safe_int(_find_val(r, "stage") or r.get("stage"))
        if ts and stage is not None:
            # Samsung sleep stages: 40001=awake, 40002=light, 40003=deep, 40004=REM
            stage_names = {40001: "awake", 40002: "light", 40003: "deep", 40004: "rem"}
            stage_name = stage_names.get(stage, str(stage))
            p = (Point("samsung_sleep_stage")
                 .tag("source", "samsung_health")
                 .tag("stage", stage_name)
                 .field("stage_code", stage)
                 .field("marker", 1)
                 .time(ts.astimezone(timezone.utc)))
            points.append(p)
    return points


def _parse_steps(rows: list[dict]) -> list[Point]:
    points = []
    for r in rows:
        ts = _find_ts(r)
        count = _safe_int(_find_val(r, "step_count") or _find_val(r, "count") or r.get("count") or r.get("step_count"))
        if ts and count and count > 0:
            p = (Point("samsung_steps")
                 .tag("source", "samsung_health")
                 .field("count", count))
            distance = _safe_float(r.get("distance"))
            if distance:
                p = p.field("distance_m", distance)
            calories = _safe_float(r.get("calorie"))
            if calories:
                p = p.field("calories", calories)
            p = p.time(ts.astimezone(timezone.utc))
            points.append(p)
    return points


def _parse_spo2(rows: list[dict]) -> list[Point]:
    points = []
    for r in rows:
        ts = _find_ts(r)
        spo2 = _safe_float(_find_val(r, "spo2") or _find_val(r, "oxygen_saturation") or r.get("spo2"))
        if ts and spo2 and spo2 > 0:
            p = (Point("samsung_spo2")
                 .tag("source", "samsung_health")
                 .field("spo2", spo2)
                 .time(ts.astimezone(timezone.utc)))
            points.append(p)
    return points


def _parse_stress(rows: list[dict]) -> list[Point]:
    points = []
    for r in rows:
        ts = _find_ts(r)
        score = _safe_int(_find_val(r, "score") or r.get("score") or r.get("max"))
        if ts and score is not None and score > 0:
            p = (Point("samsung_stress")
                 .tag("source", "samsung_health")
                 .field("score", score)
                 .time(ts.astimezone(timezone.utc)))
            points.append(p)
    return points


def _parse_exercise(rows: list[dict]) -> list[Point]:
    points = []
    for r in rows:
        ts = _find_ts(r)
        if not ts:
            continue
        p = Point("samsung_exercise").tag("source", "samsung_health")
        exercise_type = _find_val(r, "exercise_type") or r.get("exercise_type")
        if exercise_type:
            p = p.tag("exercise_type", str(exercise_type))
        duration = _safe_float(_find_val(r, "duration") or r.get("duration"))
        if duration:
            p = p.field("duration_ms", duration)
        calories = _safe_float(_find_val(r, "calorie") or r.get("calorie") or r.get("total_calorie"))
        if calories:
            p = p.field("calories", calories)
        distance = _safe_float(_find_val(r, "distance") or r.get("distance"))
        if distance:
            p = p.field("distance_m", distance)
        hr_mean = _safe_float(_find_val(r, "mean_heart_rate") or r.get("mean_heart_rate"))
        if hr_mean:
            p = p.field("mean_hr", hr_mean)
        p = p.time(ts.astimezone(timezone.utc))
        points.append(p)
    return points


def _parse_generic(rows: list[dict], measurement: str) -> list[Point]:
    """Fallback parser — imports all numeric fields as-is."""
    points = []
    for r in rows:
        ts = _parse_ts(r.get("start_time") or r.get("create_time") or r.get("update_time", ""))
        if not ts:
            continue
        p = Point(measurement).tag("source", "samsung_health")
        has_field = False
        for k, v in r.items():
            if k in ("start_time", "end_time", "create_time", "update_time", "time_offset", "deviceuuid", "pkg_name", "datauuid"):
                continue
            fv = _safe_float(v)
            if fv is not None:
                # Sanitize field name
                safe_k = k.replace("com.samsung.health.", "").replace("com.samsung.shealth.", "").replace(".", "_")
                p = p.field(safe_k, fv)
                has_field = True
        if has_field:
            p = p.time(ts.astimezone(timezone.utc))
            points.append(p)
    return points


# ---------- File type routing ----------

FILE_PARSERS: dict[str, tuple[str, Any]] = {
    "heart_rate": ("samsung_hr", _parse_heart_rate),
    "sleep_stage": ("samsung_sleep_stage", _parse_sleep_stage),
    "sleep": ("samsung_sleep", _parse_sleep),
    "step_count": ("samsung_steps", _parse_steps),
    "pedometer_day_summary": ("samsung_steps", _parse_steps),
    "blood_oxygen": ("samsung_spo2", _parse_spo2),
    "oxygen_saturation": ("samsung_spo2", _parse_spo2),
    "stress": ("samsung_stress", _parse_stress),
    "exercise": ("samsung_exercise", _parse_exercise),
}


def import_samsung_health(
    path: Path,
    include_generic: bool = False,
) -> dict[str, Any]:
    """
    Import Samsung Health data export (ZIP or extracted directory).

    Returns stats dict with per-type counts.
    """
    # Handle ZIP
    base_dir = path
    if path.suffix == ".zip":
        extract_to = path.parent / path.stem
        if not extract_to.exists():
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(extract_to)
            log.info("Extracted ZIP to %s", extract_to)
        base_dir = extract_to

    # Find all CSVs recursively
    csv_files = sorted(base_dir.rglob("*.csv"))
    log.info("Found %d CSV files in %s", len(csv_files), base_dir)

    client = InfluxDBClient(
        url=settings.influx_url,
        token=settings.influx_token,
        org=settings.influx_org,
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)

    stats: dict[str, int] = {}
    total_points = 0

    for csv_path in csv_files:
        fname = csv_path.stem.lower()

        # Match to a parser
        parser_fn = None
        measurement = None
        for key, (meas, fn) in FILE_PARSERS.items():
            if key in fname:
                parser_fn = fn
                measurement = meas
                break

        if parser_fn is None:
            if include_generic:
                # Derive measurement from filename
                measurement = "samsung_" + fname.split(".")[0].replace("com_samsung_health_", "").replace("com_samsung_shealth_", "")[:40]
                parser_fn = lambda rows, m=measurement: _parse_generic(rows, m)
            else:
                log.debug("Skipping %s (no parser, include_generic=False)", csv_path.name)
                continue

        try:
            rows = _read_samsung_csv(csv_path)
            if not rows:
                continue
            points = parser_fn(rows)
            if points:
                # Batch write
                for i in range(0, len(points), 5000):
                    write_api.write(bucket=settings.influx_bucket, record=points[i:i + 5000])
                stats[measurement] = stats.get(measurement, 0) + len(points)
                total_points += len(points)
                log.info("Imported %s: %d points from %s", measurement, len(points), csv_path.name)
        except Exception as e:
            log.error("Failed to import %s: %s", csv_path.name, e)

    client.close()

    return {
        "total_csvs": len(csv_files),
        "total_points": total_points,
        "per_type": stats,
        "base_dir": str(base_dir),
    }

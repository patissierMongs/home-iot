"""
Sleep as Android CSV → InfluxDB importer.

CSV 포맷: 각 수면 세션이 2~3줄 블록 (header row, data row, optional event row).
첫 15컬럼은 메타데이터, 그 뒤는 5분 간격 actigraphy 샘플.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS

from ..config import settings

# SaA "From"/"To" 포맷: "05. 04. 2026 4:33"  (day. month. year H:MM)
SEOUL = timezone(timedelta(hours=9))


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s.strip(), "%d. %m. %Y %H:%M").replace(tzinfo=SEOUL)


def _parse_float(s: str, default: float = 0.0) -> float:
    if s is None or s == "":
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _parse_int(s: str, default: int = 0) -> int:
    if s is None or s == "":
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def _extract_hashtags(comment: str) -> list[str]:
    return re.findall(r"#(\w+)", comment or "")


@dataclass
class SleepRecord:
    id: str
    tz: str
    start: datetime
    end: datetime
    scheduled: str
    hours: float
    rating: float
    comment: str
    tags: list[str]
    framerate: int
    snore: int
    noise: float
    cycles: int
    deep_sleep: float
    len_adjust: int
    geo: str
    actigraphy_columns: list[str]  # 시간 라벨 (e.g. "4:38")
    actigraphy_values: list[float]  # 각 시간 슬롯의 수치
    events: list[tuple[str, datetime]]  # (event_type, ts) from event row


def _parse_event_token(token: str) -> tuple[str, datetime] | None:
    """
    Sleep as Android event row tokens 형태:
      "LIGHT_START-1744887240000"  (유닉스 ms)
      "DEEP_END-1744888020000"
      "TRACKING_PAUSED-..."
    """
    if not token or "-" not in token:
        return None
    name, _, ts_str = token.rpartition("-")
    if not ts_str.isdigit():
        return None
    try:
        ts_ms = int(ts_str)
        return name, datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    except (ValueError, OSError):
        return None


def parse_csv(path: Path) -> list[SleepRecord]:
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 헤더 라인 인덱스 (각 레코드 블록 시작)
    header_idxs = [i for i, l in enumerate(lines) if l.startswith("Id,")]
    header_idxs.append(len(lines))

    records: list[SleepRecord] = []
    for i in range(len(header_idxs) - 1):
        start = header_idxs[i]
        end = header_idxs[i + 1]
        block = lines[start:end]
        if len(block) < 2:
            continue

        # Row 0: header, Row 1: data
        header = next(csv.reader(io.StringIO(block[0])))
        data = next(csv.reader(io.StringIO(block[1])))
        rec = dict(zip(header, data))

        # Event row (optional)
        events: list[tuple[str, datetime]] = []
        if len(block) >= 3:
            ev_row = next(csv.reader(io.StringIO(block[2])), [])
            for tok in ev_row:
                parsed = _parse_event_token(tok)
                if parsed:
                    events.append(parsed)

        # Actigraphy: header index 15 이후, "Event" 라벨로 표기된 컬럼 제외
        acti_cols: list[str] = []
        acti_vals: list[float] = []
        for col_idx, col_name in enumerate(header[15:], start=15):
            if col_name == "Event":
                continue
            val = data[col_idx] if col_idx < len(data) else ""
            if val == "":
                continue
            acti_cols.append(col_name)
            try:
                acti_vals.append(float(val))
            except ValueError:
                pass

        try:
            start_dt = _parse_dt(rec["From"])
            end_dt = _parse_dt(rec["To"])
        except (ValueError, KeyError):
            continue

        records.append(
            SleepRecord(
                id=rec.get("Id", "").strip('"'),
                tz=rec.get("Tz", "Asia/Seoul"),
                start=start_dt,
                end=end_dt,
                scheduled=rec.get("Sched", ""),
                hours=_parse_float(rec.get("Hours", "0")),
                rating=_parse_float(rec.get("Rating", "0")),
                comment=rec.get("Comment", ""),
                tags=_extract_hashtags(rec.get("Comment", "")),
                framerate=_parse_int(rec.get("Framerate", "0")),
                snore=_parse_int(rec.get("Snore", "-1")),
                noise=_parse_float(rec.get("Noise", "-1")),
                cycles=_parse_int(rec.get("Cycles", "0")),
                deep_sleep=_parse_float(rec.get("DeepSleep", "0")),
                len_adjust=_parse_int(rec.get("LenAdjust", "0")),
                geo=rec.get("Geo", ""),
                actigraphy_columns=acti_cols,
                actigraphy_values=acti_vals,
                events=events,
            )
        )

    return records


def _acti_timestamps(rec: SleepRecord) -> list[datetime]:
    """
    actigraphy_columns 는 "H:MM" 형식. 세션이 자정을 넘어가면 날짜가 바뀜.
    rec.start 부터 시작해서 시간이 감소하면 다음 날로 넘어간 것으로 간주.
    """
    if not rec.actigraphy_columns:
        return []
    base = rec.start
    ts: list[datetime] = []
    prev_mins = -1
    day_offset = 0
    for col in rec.actigraphy_columns:
        try:
            h, m = map(int, col.split(":"))
        except ValueError:
            ts.append(base)
            continue
        mins = h * 60 + m
        if prev_mins != -1 and mins < prev_mins - 30:  # 자정 넘은 롤오버 감지
            day_offset += 1
        prev_mins = mins
        ts.append(
            rec.start.replace(hour=h, minute=m, second=0, microsecond=0)
            + timedelta(days=day_offset)
        )
    return ts


def import_to_influx(
    csv_path: Path,
    include_actigraphy: bool = True,
    include_events: bool = True,
) -> dict:
    records = parse_csv(csv_path)

    client = InfluxDBClient(
        url=settings.influx_url,
        token=settings.influx_token,
        org=settings.influx_org,
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)

    session_points: list[Point] = []
    actigraphy_points: list[Point] = []
    event_points: list[Point] = []

    for r in records:
        p = (
            Point("sleep_session")
            .tag("source", "sleep_as_android")
            .tag("session_id", r.id)
            .tag("tz", r.tz)
            .tag("geo", r.geo or "unknown")
            .field("hours", float(r.hours))
            .field("rating", float(r.rating))
            .field("cycles", int(r.cycles))
            .field("deep_sleep", float(r.deep_sleep))
            .field("snore", int(r.snore))
            .field("noise", float(r.noise))
            .field("len_adjust", int(r.len_adjust))
            .field("comment", r.comment)
            .field("tags_csv", ",".join(r.tags))
            .time(r.start.astimezone(timezone.utc))
        )
        # 태그별로 bool 필드로도 넣으면 Grafana 필터 편함
        for t in set(r.tags):
            p = p.field(f"tag_{t}", True)
        session_points.append(p)

        if include_actigraphy:
            for ts, val in zip(_acti_timestamps(r), r.actigraphy_values):
                actigraphy_points.append(
                    Point("sleep_actigraphy")
                    .tag("session_id", r.id)
                    .field("activity", float(val))
                    .time(ts.astimezone(timezone.utc))
                )

        if include_events:
            for etype, ets in r.events:
                event_points.append(
                    Point("sleep_events")
                    .tag("session_id", r.id)
                    .tag("event", etype)
                    .field("marker", 1)
                    .time(ets)
                )

    # 배치 쓰기
    def _write(points: list[Point], label: str):
        if not points:
            return 0
        # 5000 단위로 쪼개서 쓰기 (InfluxDB v2 기본 batch 한도 여유)
        total = 0
        for i in range(0, len(points), 5000):
            write_api.write(bucket=settings.influx_bucket, record=points[i : i + 5000])
            total += len(points[i : i + 5000])
        return total

    stats = {
        "records": len(records),
        "sessions_written": _write(session_points, "sessions"),
        "actigraphy_written": _write(actigraphy_points, "actigraphy") if include_actigraphy else 0,
        "events_written": _write(event_points, "events") if include_events else 0,
        "earliest": min(r.start for r in records).isoformat() if records else None,
        "latest": max(r.start for r in records).isoformat() if records else None,
    }

    client.close()
    return stats

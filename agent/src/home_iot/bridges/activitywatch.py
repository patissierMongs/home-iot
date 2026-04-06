"""
ActivityWatch → InfluxDB (+ MQTT) 브리지.

AW의 REST API에서 window/afk/browser 버킷 이벤트를 폴링해서:
  1. InfluxDB measurement로 직접 기록 (장기 분석용)
  2. 현재 상태를 MQTT retained 토픽으로 publish (에이전트 실시간 접근용)

AW 이벤트 형식:
  {
    "id": int,
    "timestamp": ISO8601,
    "duration": float (seconds),
    "data": {...}
  }

InfluxDB 스키마:
  measurement: activity_window
    tags: host, app, category(=app root 또는 classified)
    fields: title, duration_s
    time: event timestamp

  measurement: activity_afk
    tags: host, status (afk|not-afk)
    fields: duration_s
    time: event timestamp

  measurement: activity_browser
    tags: host, domain
    fields: title, url, duration_s, audible, incognito
    time: event timestamp

MQTT 토픽 (모두 retain=true):
  home-iot/activity/window       현재 활성 앱/제목 JSON
  home-iot/activity/afk          현재 afk 상태 JSON
  home-iot/activity/browser      현재 브라우저 탭 JSON
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from ..config import settings

log = structlog.get_logger(__name__)


AW_URL = "http://localhost:5600"   # WSL mirrored networking 덕에 바로 접근
POLL_INTERVAL = 5  # 초
BACKFILL_SAFE_MARGIN = timedelta(seconds=10)  # 중복 방지용


def _extract_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or "unknown"
    except Exception:
        return "unknown"


class ActivityWatchBridge:
    def __init__(self, mqtt_client=None) -> None:
        self._http = httpx.AsyncClient(base_url=AW_URL, timeout=10.0)
        self._influx = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
        )
        self._write = self._influx.write_api(write_options=SYNCHRONOUS)
        self._mqtt = mqtt_client
        # 버킷별 마지막으로 처리한 timestamp (중복 방지)
        self._last_ts: dict[str, datetime] = {}
        self._hostname: str | None = None

    async def aclose(self) -> None:
        await self._http.aclose()
        self._influx.close()

    async def _get_buckets(self) -> dict[str, dict[str, Any]]:
        resp = await self._http.get("/api/0/buckets/")
        resp.raise_for_status()
        return resp.json()

    async def _get_events(
        self, bucket_id: str, start: datetime | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start.isoformat()
        resp = await self._http.get(f"/api/0/buckets/{bucket_id}/events", params=params)
        resp.raise_for_status()
        return resp.json()

    async def _publish_mqtt(self, topic: str, payload: dict[str, Any]) -> None:
        if self._mqtt is None:
            return
        try:
            await self._mqtt.publish(topic, json.dumps(payload, ensure_ascii=False), retain=True)
        except Exception as e:
            log.warning("aw.mqtt_publish_failed", topic=topic, error=str(e))

    # ---------- 버킷별 이벤트 → InfluxDB Point 변환 ----------

    def _window_point(self, ev: dict[str, Any], host: str) -> Point:
        data = ev.get("data", {})
        app = data.get("app", "unknown")
        title = data.get("title", "")
        ts = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
        return (
            Point("activity_window")
            .tag("host", host)
            .tag("app", app)
            .field("title", title[:500])
            .field("duration_s", float(ev.get("duration", 0)))
            .time(ts)
        )

    def _afk_point(self, ev: dict[str, Any], host: str) -> Point:
        data = ev.get("data", {})
        status = data.get("status", "unknown")
        ts = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
        return (
            Point("activity_afk")
            .tag("host", host)
            .tag("status", status)
            .field("duration_s", float(ev.get("duration", 0)))
            .time(ts)
        )

    def _browser_point(self, ev: dict[str, Any], host: str) -> Point:
        data = ev.get("data", {})
        url = data.get("url", "")
        title = data.get("title", "")
        domain = _extract_domain(url)
        ts = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
        return (
            Point("activity_browser")
            .tag("host", host)
            .tag("domain", domain)
            .field("title", title[:500])
            .field("url", url[:1000])
            .field("duration_s", float(ev.get("duration", 0)))
            .field("audible", bool(data.get("audible", False)))
            .field("incognito", bool(data.get("incognito", False)))
            .time(ts)
        )

    async def _process_bucket(self, bucket_id: str, bucket_type: str, host: str) -> int:
        """한 버킷의 신규 이벤트를 처리. 처리 건수 반환."""
        last = self._last_ts.get(bucket_id)
        start = (last - BACKFILL_SAFE_MARGIN) if last else datetime.now(timezone.utc) - timedelta(minutes=15)

        events = await self._get_events(bucket_id, start=start, limit=500)
        if not events:
            return 0

        points = []
        for ev in events:
            ts = datetime.fromisoformat(ev["timestamp"].replace("Z", "+00:00"))
            if last and ts <= last:
                continue
            if bucket_type == "currentwindow":
                points.append(self._window_point(ev, host))
            elif bucket_type == "afkstatus":
                points.append(self._afk_point(ev, host))
            elif bucket_type.startswith("web.tab"):
                points.append(self._browser_point(ev, host))

        if points:
            self._write.write(bucket=settings.influx_bucket, record=points)
            self._last_ts[bucket_id] = max(
                datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")) for e in events
            )

        # 최신 이벤트 하나를 MQTT로 retained publish
        latest = events[0]  # AW는 최신순 정렬
        if bucket_type == "currentwindow":
            await self._publish_mqtt(
                "home-iot/activity/window",
                {
                    "app": latest["data"].get("app"),
                    "title": latest["data"].get("title"),
                    "duration_s": latest.get("duration", 0),
                    "ts": latest["timestamp"],
                    "host": host,
                },
            )
        elif bucket_type == "afkstatus":
            await self._publish_mqtt(
                "home-iot/activity/afk",
                {
                    "status": latest["data"].get("status"),
                    "duration_s": latest.get("duration", 0),
                    "ts": latest["timestamp"],
                    "host": host,
                },
            )
        elif bucket_type.startswith("web.tab"):
            await self._publish_mqtt(
                "home-iot/activity/browser",
                {
                    "url": latest["data"].get("url"),
                    "title": latest["data"].get("title"),
                    "domain": _extract_domain(latest["data"].get("url", "")),
                    "duration_s": latest.get("duration", 0),
                    "ts": latest["timestamp"],
                    "host": host,
                },
            )

        return len(points)

    async def run(self) -> None:
        log.info("aw.bridge.starting", aw_url=AW_URL, interval=POLL_INTERVAL)
        while True:
            try:
                buckets = await self._get_buckets()
                for bid, info in buckets.items():
                    btype = info.get("type", "")
                    host = info.get("hostname") or "unknown"
                    if host == "unknown":
                        continue
                    if btype not in ("currentwindow", "afkstatus") and not btype.startswith("web.tab"):
                        continue
                    try:
                        n = await self._process_bucket(bid, btype, host)
                        if n:
                            log.debug("aw.bucket.processed", bucket=bid, points=n)
                    except Exception as e:
                        log.error("aw.bucket.error", bucket=bid, error=str(e))
            except httpx.RequestError as e:
                log.warning("aw.unreachable", error=str(e))
            except Exception as e:
                log.exception("aw.loop_error", error=str(e))

            await asyncio.sleep(POLL_INTERVAL)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )
    bridge = ActivityWatchBridge()
    try:
        await bridge.run()
    except KeyboardInterrupt:
        pass
    finally:
        await bridge.aclose()


if __name__ == "__main__":
    asyncio.run(main())

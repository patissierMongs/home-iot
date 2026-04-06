"""
LLM 에이전트가 호출할 수 있는 도구(tool) 정의와 구현.

- OpenAI/Ollama 호환 tool schema로 표기
- 같은 함수 본체를 나중에 MCP 서버에서도 재사용
- request_approval은 Channels 패턴을 빌려온 안전 경계용 도구
- InfluxDB 쿼리 도구는 LLM이 과거 데이터를 읽고 추론할 때 사용
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog
from influxdb_client import InfluxDBClient

from .config import settings
from .ha import HAClient

# Knowledge YAML file paths (under agent/config/)
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
_LAYOUT_PATH = _CONFIG_DIR / "home_layout.yaml"
_KNOWLEDGE_PATH = _CONFIG_DIR / "home_knowledge.yaml"
_QUESTIONS_PATH = _CONFIG_DIR / "open_questions.yaml"

log = structlog.get_logger(__name__)


# ---------------- Tool schemas (Ollama/OpenAI compatible) ----------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    # ---- Home Assistant control ----
    {
        "type": "function",
        "function": {
            "name": "ha_list_entities",
            "description": "List Home Assistant entities. Filter by domain (light/switch/sensor/etc.) or omit for all.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "HA domain filter (light, switch, sensor, binary_sensor, cover, etc.). Omit for all domains.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_get_state",
            "description": "Get the current state and all attributes of a specific entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Entity id (e.g. light.hue_color_lamp_2, sensor.keompyuteo_onseubdo_temperature).",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_call_service",
            "description": (
                "Call a Home Assistant service to control a device. "
                "Example: turn on a light with domain=light, service=turn_on, entity_id='light.x'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Service domain (light, switch, cover, scene, ...)."},
                    "service": {"type": "string", "description": "Service name (turn_on, turn_off, toggle, set_cover_position, ...)."},
                    "entity_id": {"type": "string", "description": "Target entity id."},
                    "data": {
                        "type": "object",
                        "description": "Optional data (brightness_pct, color_name, position, etc.).",
                    },
                },
                "required": ["domain", "service", "entity_id"],
            },
        },
    },
    # ---- History / analytics ----
    {
        "type": "function",
        "function": {
            "name": "query_influx",
            "description": (
                "Aggregated time-series query against InfluxDB. "
                "measurement can be an HA entity_id (e.g. 'sensor.keompyuteo_onseubdo_temperature') "
                "or a custom measurement (sleep_session, sleep_actigraphy, activity_window, activity_afk, activity_browser, cpu, mem, nvidia_smi, docker_container_*, ...). "
                "since/until accept relative ('-7d', '-24h', 'now') or ISO8601. aggregate is one of mean/sum/max/min/count/last."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "measurement": {"type": "string", "description": "Measurement name (entity_id or custom)."},
                    "field": {"type": "string", "description": "Field to read. Default 'value'.", "default": "value"},
                    "since": {"type": "string", "description": "Start time.", "default": "-24h"},
                    "until": {"type": "string", "description": "End time.", "default": "now"},
                    "aggregate": {"type": "string", "description": "Aggregation function.", "default": "mean"},
                    "every": {"type": "string", "description": "Window size (e.g. 5m, 1h, 1d).", "default": "1h"},
                },
                "required": ["measurement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sleep_stats",
            "description": (
                "Daily-aggregated sleep statistics for the last N days. "
                "IMPORTANT: returns per-calendar-day totals (morning sessions attributed to previous night), "
                "not per-session averages. Fields: days_with_record, coverage_pct, daily_avg_hours, "
                "daily_min_hours, daily_max_hours, avg_deep_sleep_pct, avg_cycles_per_session, total_hours."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Window in days.", "default": 7},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_activity",
            "description": "List of recently focused apps/windows from ActivityWatch (last N minutes). Use when you need to know what the user was doing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {"type": "integer", "description": "Window in minutes.", "default": 15},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity_summary",
            "description": "Per-app total focus time (seconds) over the last N days, sorted descending. Use for work-pattern / time-allocation analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Window in days.", "default": 1},
                    "top_n": {"type": "integer", "description": "Top N apps.", "default": 15},
                },
            },
        },
    },
    # ---- Location analytics ----
    {
        "type": "function",
        "function": {
            "name": "get_top_visited_places",
            "description": (
                "Aggregate timeline_visit data: returns top N most-visited places with visit count, "
                "average stay duration, total hours, GPS coordinates, semantic_type (INFERRED_HOME, etc.), "
                "and last visit time. Use for 'where do I go most?' questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Look-back window in days.", "default": 90},
                    "top_n": {"type": "integer", "description": "Top N places.", "default": 15},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_location_trail",
            "description": (
                "Get GPS breadcrumb trail from timeline_gps for map visualization. "
                "Returns lat/lon/time arrays. Use with create_map(path=...) for route visualization, "
                "or create_map(heatmap=...) for density maps."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Look-back window.", "default": 7},
                    "max_points": {"type": "integer", "description": "Max GPS points to return.", "default": 500},
                },
            },
        },
    },
    # ---- Home context + knowledge base ----
    {
        "type": "function",
        "function": {
            "name": "get_home_context",
            "description": (
                "Returns the merged home context: layout (zones, devices, habits, safety boundaries) from "
                "home_layout.yaml AND accumulated knowledge (entity_dictionary, observations, preferences, "
                "patterns, lessons) from home_knowledge.yaml, plus currently open questions. "
                "**Always call this first** before spatial reasoning or situation judgment. "
                "Pass a section name to get only part of it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "Optional section filter. One of: home, zones, device_notes, habits, safety_boundaries, data_sources, entity_dictionary, observations, preferences, patterns, lessons, open_questions.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_observation",
            "description": (
                "Append a newly observed or confirmed fact to home_knowledge.yaml. "
                "Use when you discover something reusable during analysis or conversation. "
                "Examples: 'user prefers X', 'device Y's state reporting is unreliable', 'pattern Z appears on weekdays'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Short topic (e.g. 'Sleep data interpretation', 'Curtain direction issue')."},
                    "claim": {"type": "string", "description": "The observed fact or claim."},
                    "evidence": {"type": "string", "description": "How you know — data source, user quote, query result, etc."},
                    "source": {"type": "string", "description": "One of: user | observed | inferred | imported.", "default": "observed"},
                    "confidence": {"type": "number", "description": "0.0 to 1.0.", "default": 0.8},
                },
                "required": ["topic", "claim", "evidence"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_entity_dictionary",
            "description": (
                "Add or update an entry in the entity decoder dictionary. "
                "Use this whenever you learn what an entity_id actually represents — its role, physical location, quirks. "
                "Example: user says 'light.hue_color_lamp_2 is the bathroom light' -> call this to persist it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "role": {"type": "string", "description": "What the device does."},
                    "location": {"type": "string", "description": "Physical location (zone name or room)."},
                    "note": {"type": "string", "description": "Extra notes or quirks."},
                    "source": {"type": "string", "default": "user"},
                    "confidence": {"type": "number", "default": 1.0},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_preference",
            "description": "Persist a user preference or habit. Use when the user states 'I like X', 'I prefer Y', 'never do Z'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Preference category (e.g. humidity, sleep_time, communication_style)."},
                    "value": {"type": "string", "description": "The preference content."},
                    "source": {"type": "string", "default": "user"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_open_question",
            "description": (
                "Queue a question to ask the user later. "
                "**If the user is in the conversation right now and answering is natural, ask directly and then call "
                "update_entity_dictionary / record_observation / record_preference with the answer instead.** "
                "This tool is for things you'd like to know but can't ask right now without derailing the task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question (write it in Korean — it will be shown to the user)."},
                    "context": {"type": "string", "description": "Why it matters and what would improve if answered."},
                    "priority": {"type": "string", "description": "high | medium | low.", "default": "medium"},
                },
                "required": ["question", "context"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_open_questions",
            "description": "Return the list of currently open questions. Call at conversation start to see what you've been wondering about and raise questions at natural moments.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer_question",
            "description": (
                "Mark a pending question as answered. The answer is simultaneously recorded to knowledge "
                "(observation, entity_dictionary, or preference depending on record_as). Provide entity_id "
                "if record_as is entity_dictionary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "string", "description": "Question id (e.g. Q001)."},
                    "answer": {"type": "string", "description": "The user's answer."},
                    "record_as": {
                        "type": "string",
                        "description": "Where to additionally record the answer: observation | entity_dictionary | preference.",
                        "default": "observation",
                    },
                    "entity_id": {"type": "string", "description": "Required when record_as is 'entity_dictionary'."},
                },
                "required": ["question_id", "answer"],
            },
        },
    },
    # ---- Safety gating ----
    {
        "type": "function",
        "function": {
            "name": "request_approval",
            "description": (
                "Request user approval before performing a sensitive action (door locks, irreversible device changes, fingerbot triggers, large-scale off). "
                "Only proceed with the action if the return value indicates approved=true."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "Natural-language description of the proposed action."},
                    "reason": {"type": "string", "description": "Why this action is needed."},
                },
                "required": ["action", "reason"],
            },
        },
    },
]


# ---------------- Tool 구현 ----------------


class Tools:
    """도구의 실제 실행 본체. LLM 어댑터와 MCP 서버가 공유."""

    def __init__(self, ha: HAClient) -> None:
        self.ha = ha
        self._influx = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
        )
        self._query_api = self._influx.query_api()

    # ---------- HA ----------
    async def ha_list_entities(self, domain: str | None = None) -> list[dict[str, str]]:
        return await self.ha.list_entities(domain)

    async def ha_get_state(self, entity_id: str) -> dict[str, Any]:
        return await self.ha.get_state(entity_id)

    async def ha_call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = {"entity_id": entity_id}
        result = await self.ha.call_service(domain, service, target=target, data=data)
        log.info("tool.ha_call_service", domain=domain, service=service, entity=entity_id, data=data)
        return {"ok": True, "affected": len(result)}

    # ---------- InfluxDB (동기 API — asyncio thread executor로 비블로킹 실행) ----------

    async def _run_flux(self, flux: str) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        def _sync():
            tables = self._query_api.query(flux)
            rows: list[dict[str, Any]] = []
            for table in tables:
                for record in table.records:
                    values = record.values
                    t = values.get("_time")
                    rows.append({
                        "time": t.isoformat() if t else None,
                        "value": values.get("_value"),
                        "field": values.get("_field"),
                        "measurement": values.get("_measurement"),
                        **{k: v for k, v in values.items() if k not in ("_time", "_value", "_field", "_measurement", "result", "table", "_start", "_stop")},
                    })
            return rows
        return await loop.run_in_executor(None, _sync)

    async def query_influx(
        self,
        measurement: str,
        field: str = "value",
        since: str = "-24h",
        until: str = "now",
        aggregate: str = "mean",
        every: str = "1h",
    ) -> dict[str, Any]:
        # since/until normalization
        range_line = f'|> range(start: {since}, stop: {until})' if until != "now" else f'|> range(start: {since})'
        flux = f"""
from(bucket: "{settings.influx_bucket}")
  {range_line}
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => r._field == "{field}")
  |> aggregateWindow(every: {every}, fn: {aggregate}, createEmpty: false)
  |> yield(name: "{aggregate}")
"""
        rows = await self._run_flux(flux)
        return {
            "measurement": measurement,
            "field": field,
            "points": len(rows),
            "data": [{"t": r["time"], "v": r["value"]} for r in rows[:200]],  # 200 포인트 상한
        }

    async def get_sleep_stats(self, days: int = 7) -> dict[str, Any]:
        """
        일별 총합으로 집계한 수면 통계.

        Sleep as Android는 밤에 pause/resume 시 한 "잠"을 여러 세션으로 나누기 때문에,
        세션 평균은 오해의 소지가 있음. 이 도구는 **calendar day 기준 일별 총합**을 계산.
        기상 시각이 정오 이전이면 "전날 밤"으로 귀속 (새벽 2시 취침 = 전날).
        """
        # 1) 세션별 hours를 전부 가져오고 파이썬에서 일별 집계
        flux = f"""
from(bucket: "{settings.influx_bucket}")
  |> range(start: -{days + 2}d)
  |> filter(fn: (r) => r._measurement == "sleep_session")
  |> filter(fn: (r) => r._field == "hours" or r._field == "deep_sleep" or r._field == "cycles")
  |> filter(fn: (r) => r._value >= 0)
  |> keep(columns: ["_time", "_value", "_field", "session_id"])
"""
        rows = await self._run_flux(flux)

        from collections import defaultdict
        from datetime import datetime, timedelta

        by_day_hours: dict[Any, float] = defaultdict(float)
        by_day_deep: dict[Any, list[float]] = defaultdict(list)
        by_day_cycles: dict[Any, list[int]] = defaultdict(list)

        for r in rows:
            t = r.get("time")
            if not t:
                continue
            dt = datetime.fromisoformat(t)
            sleep_day = (dt - timedelta(days=1)).date() if dt.hour < 12 else dt.date()
            field = r["field"]
            val = r["value"]
            if val is None:
                continue
            if field == "hours":
                by_day_hours[sleep_day] += float(val)
            elif field == "deep_sleep":
                by_day_deep[sleep_day].append(float(val))
            elif field == "cycles":
                by_day_cycles[sleep_day].append(int(val))

        # 요청한 days 범위로 자르기 (오늘부터 N일 전까지)
        from datetime import date
        today = date.today()
        window = [today - timedelta(days=i) for i in range(days)]
        days_with_data = [d for d in window if d in by_day_hours]

        if not days_with_data:
            return {"days": days, "days_with_record": 0}

        total_h = sum(by_day_hours[d] for d in days_with_data)
        avg_deep = sum(sum(by_day_deep[d]) / len(by_day_deep[d]) for d in days_with_data if by_day_deep[d]) / max(1, len([d for d in days_with_data if by_day_deep[d]]))
        avg_cycles = sum(sum(by_day_cycles[d]) for d in days_with_data) / max(1, sum(len(by_day_cycles[d]) for d in days_with_data))

        return {
            "days": days,
            "days_with_record": len(days_with_data),
            "coverage_pct": round(len(days_with_data) / days * 100, 1),
            "daily_avg_hours": round(total_h / len(days_with_data), 2),
            "daily_min_hours": round(min(by_day_hours[d] for d in days_with_data), 2),
            "daily_max_hours": round(max(by_day_hours[d] for d in days_with_data), 2),
            "avg_deep_sleep_pct": round(avg_deep * 100, 1),
            "avg_cycles_per_session": round(avg_cycles, 2),
            "total_hours": round(total_h, 1),
        }

    async def get_recent_activity(self, minutes: int = 15) -> dict[str, Any]:
        flux = f"""
from(bucket: "{settings.influx_bucket}")
  |> range(start: -{minutes}m)
  |> filter(fn: (r) => r._measurement == "activity_window" and r._field == "title")
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 50)
"""
        rows = await self._run_flux(flux)
        items = []
        for r in rows:
            items.append({
                "t": r["time"],
                "app": r.get("app"),
                "title": r["value"],
            })
        return {"minutes": minutes, "count": len(items), "items": items}

    async def get_activity_summary(self, days: int = 1, top_n: int = 15) -> dict[str, Any]:
        flux = f"""
from(bucket: "{settings.influx_bucket}")
  |> range(start: -{days}d)
  |> filter(fn: (r) => r._measurement == "activity_window" and r._field == "duration_s")
  |> group(columns: ["app"])
  |> sum()
  |> sort(columns: ["_value"], desc: true)
  |> limit(n: {top_n})
"""
        rows = await self._run_flux(flux)
        return {
            "days": days,
            "apps": [
                {"app": r.get("app", "unknown"), "seconds": round(float(r["value"]), 0)}
                for r in rows
            ],
        }

    # ---------- Location analytics ----------

    async def _reverse_geocode(self, lat: float, lon: float) -> dict[str, str]:
        """Reverse geocode via Nominatim (free, no API key). Rate: 1 req/sec."""
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient() as c:
                r = await c.get(
                    f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&accept-language=ko",
                    headers={"User-Agent": "home-iot/1.0"}, timeout=10.0,
                )
                d = r.json()
                addr = d.get("address", {})
                name = addr.get("amenity") or addr.get("shop") or addr.get("building") or addr.get("leisure") or ""
                road = addr.get("road", "")
                city = addr.get("city") or addr.get("county") or addr.get("town") or ""
                return {"name": name, "road": road, "city": city, "full": d.get("display_name", "")[:120]}
        except Exception:
            return {"name": "", "road": "", "city": "", "full": ""}

    async def get_top_visited_places(self, days: int = 90, top_n: int = 15) -> dict[str, Any]:
        """Aggregate timeline_visit data by place_id, return top N most visited places with visit counts, avg duration, coordinates, semantic type, AND reverse-geocoded address/name."""
        flux = f"""
from(bucket: "{settings.influx_bucket}")
  |> range(start: -{days}d)
  |> filter(fn: (r) => r._measurement == "timeline_visit")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "place_id", "latitude", "longitude", "duration_min", "probability", "semantic_type"])
"""
        rows = await self._run_flux(flux)

        from collections import defaultdict
        places: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_duration": 0.0, "lat": None, "lon": None, "semantic_type": "", "last_visit": ""})

        for r in rows:
            pid = r.get("place_id") or r.get("value")
            if not pid or pid == "":
                continue
            p = places[pid]
            p["count"] += 1
            dur = r.get("duration_min")
            if dur and isinstance(dur, (int, float)):
                p["total_duration"] += float(dur)
            lat = r.get("latitude")
            lon = r.get("longitude")
            if lat and lon:
                p["lat"] = float(lat)
                p["lon"] = float(lon)
            st = r.get("semantic_type")
            if st:
                p["semantic_type"] = st
            t = r.get("time")
            if t and t > p["last_visit"]:
                p["last_visit"] = t

        ranked = sorted(places.items(), key=lambda x: -x[1]["count"])[:top_n]

        # Reverse geocode top places (with rate limiting)
        import asyncio as _aio
        result_places = []
        for i, (pid, info) in enumerate(ranked):
            geo = {"name": "", "road": "", "city": "", "full": ""}
            if info["lat"] and info["lon"]:
                geo = await self._reverse_geocode(info["lat"], info["lon"])
                if i < top_n - 1:
                    await _aio.sleep(1.05)  # Nominatim: max 1 req/sec

            place_name = geo["name"] or info["semantic_type"] or f"Place {i+1}"
            result_places.append({
                "rank": i + 1,
                "place_id": pid,
                "name": place_name,
                "address": geo["full"],
                "road": geo["road"],
                "city": geo["city"],
                "visits": info["count"],
                "avg_duration_min": round(info["total_duration"] / info["count"], 1) if info["count"] > 0 else 0,
                "total_hours": round(info["total_duration"] / 60, 1),
                "lat": info["lat"],
                "lon": info["lon"],
                "semantic_type": info["semantic_type"],
                "last_visit": info["last_visit"],
            })

        return {
            "days": days,
            "total_unique_places": len(places),
            "total_visits": sum(p["count"] for p in places.values()),
            "top_places": result_places,
        }

    async def get_location_trail(self, days: int = 7, max_points: int = 500) -> dict[str, Any]:
        """Get GPS trail points from timeline_gps for map visualization."""
        flux = f"""
from(bucket: "{settings.influx_bucket}")
  |> range(start: -{days}d)
  |> filter(fn: (r) => r._measurement == "timeline_gps" and r._field == "latitude")
  |> keep(columns: ["_time", "_value"])
  |> sort(columns: ["_time"])
  |> limit(n: {max_points * 2})
"""
        lat_rows = await self._run_flux(flux)

        flux_lon = f"""
from(bucket: "{settings.influx_bucket}")
  |> range(start: -{days}d)
  |> filter(fn: (r) => r._measurement == "timeline_gps" and r._field == "longitude")
  |> keep(columns: ["_time", "_value"])
  |> sort(columns: ["_time"])
  |> limit(n: {max_points * 2})
"""
        lon_rows = await self._run_flux(flux_lon)

        # Match by timestamp
        lon_map = {r["time"]: r["value"] for r in lon_rows if r.get("time")}
        points = []
        for r in lat_rows:
            t = r.get("time")
            lat = r.get("value")
            lon = lon_map.get(t)
            if lat and lon and t:
                points.append({"lat": float(lat), "lon": float(lon), "time": t})
                if len(points) >= max_points:
                    break

        return {"days": days, "point_count": len(points), "points": points}

    # ---------- 집 컨텍스트 ----------
    # ---- YAML 읽기/쓰기 헬퍼 ----
    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        import yaml
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _save_yaml(path: Path, data: dict[str, Any]) -> None:
        import yaml
        from datetime import datetime
        # metadata 자동 업데이트
        if "metadata" in data and isinstance(data["metadata"], dict):
            data["metadata"]["last_updated"] = datetime.now().isoformat()
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    async def get_home_context(self, section: str | None = None) -> dict[str, Any]:
        """layout + knowledge + open_questions를 병합해서 반환. 매 호출마다 파일 재읽기."""
        try:
            import yaml  # noqa: F401
        except ImportError:
            return {"error": "pyyaml 미설치"}

        layout = self._load_yaml(_LAYOUT_PATH)
        knowledge = self._load_yaml(_KNOWLEDGE_PATH)
        questions = self._load_yaml(_QUESTIONS_PATH)

        # 병합: layout이 기본, knowledge에서 발견된 필드는 덮어쓰지 않고 추가 키로
        merged: dict[str, Any] = dict(layout)
        for key in ("entity_dictionary", "observations", "preferences", "patterns", "lessons"):
            if key in knowledge:
                merged[key] = knowledge[key]
        merged["open_questions"] = [q for q in questions.get("questions", []) if q.get("status", "open") == "open"]

        if section in (None, "", "None", "null", "none"):
            return merged
        return {"section": section, "value": merged.get(section, f"(no such section: {section})")}

    async def record_observation(
        self,
        topic: str,
        claim: str,
        evidence: str,
        source: str = "observed",
        confidence: float = 0.8,
    ) -> dict[str, Any]:
        from datetime import date
        k = self._load_yaml(_KNOWLEDGE_PATH)
        obs_list = k.setdefault("observations", [])
        # 새 ID 생성
        existing_ids = [o.get("id", "") for o in obs_list if isinstance(o, dict)]
        num = max(
            [int(x[1:]) for x in existing_ids if x.startswith("O") and x[1:].isdigit()],
            default=0,
        ) + 1
        new_obs = {
            "id": f"O{num:03d}",
            "date": date.today().isoformat(),
            "topic": topic,
            "claim": claim,
            "evidence": evidence,
            "source": source,
            "confidence": float(confidence),
        }
        obs_list.append(new_obs)
        self._save_yaml(_KNOWLEDGE_PATH, k)
        log.info("knowledge.observation_recorded", id=new_obs["id"], topic=topic)
        return {"recorded": new_obs["id"], "path": str(_KNOWLEDGE_PATH.name)}

    async def update_entity_dictionary(
        self,
        entity_id: str,
        role: str | None = None,
        location: str | None = None,
        note: str | None = None,
        source: str = "user",
        confidence: float = 1.0,
    ) -> dict[str, Any]:
        from datetime import date
        k = self._load_yaml(_KNOWLEDGE_PATH)
        ed = k.setdefault("entity_dictionary", {})
        existing = ed.get(entity_id, {}) or {}
        entry = dict(existing)
        if role is not None:
            entry["role"] = role
        if location is not None:
            entry["location"] = location
        if note is not None:
            # append-only note
            prev_note = entry.get("note", "")
            entry["note"] = f"{prev_note}\n{note}".strip() if prev_note else note
        entry["source"] = source
        entry["confidence"] = float(confidence)
        entry["updated"] = date.today().isoformat()
        ed[entity_id] = entry
        self._save_yaml(_KNOWLEDGE_PATH, k)
        log.info("knowledge.entity_updated", entity=entity_id)
        return {"entity_id": entity_id, "entry": entry}

    async def record_preference(self, key: str, value: str, source: str = "user") -> dict[str, Any]:
        from datetime import date
        k = self._load_yaml(_KNOWLEDGE_PATH)
        prefs = k.setdefault("preferences", {})
        prefs[key] = {"value": value, "source": source, "date": date.today().isoformat()}
        self._save_yaml(_KNOWLEDGE_PATH, k)
        log.info("knowledge.preference_recorded", key=key)
        return {"key": key, "value": value}

    async def add_open_question(
        self,
        question: str,
        context: str,
        priority: str = "medium",
    ) -> dict[str, Any]:
        from datetime import date
        q_file = self._load_yaml(_QUESTIONS_PATH)
        q_list = q_file.setdefault("questions", [])
        existing_ids = [q.get("id", "") for q in q_list if isinstance(q, dict)]
        num = max(
            [int(x[1:]) for x in existing_ids if x.startswith("Q") and x[1:].isdigit()],
            default=0,
        ) + 1
        new_q = {
            "id": f"Q{num:03d}",
            "date": date.today().isoformat(),
            "question": question,
            "context": context,
            "priority": priority,
            "status": "open",
        }
        q_list.append(new_q)
        self._save_yaml(_QUESTIONS_PATH, q_file)
        log.info("knowledge.question_added", id=new_q["id"])
        return {"added": new_q["id"], "question": question}

    async def list_open_questions(self) -> dict[str, Any]:
        q_file = self._load_yaml(_QUESTIONS_PATH)
        open_qs = [q for q in q_file.get("questions", []) if q.get("status", "open") == "open"]
        return {"count": len(open_qs), "questions": open_qs}

    async def answer_question(
        self,
        question_id: str,
        answer: str,
        record_as: str = "observation",
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        q_file = self._load_yaml(_QUESTIONS_PATH)
        q_list = q_file.get("questions", [])
        target = None
        for q in q_list:
            if q.get("id") == question_id:
                target = q
                break
        if target is None:
            return {"error": f"question {question_id} not found"}

        from datetime import date
        target["status"] = "answered"
        target["answered_at"] = date.today().isoformat()
        target["answer"] = answer
        self._save_yaml(_QUESTIONS_PATH, q_file)

        # 답을 knowledge에도 기록
        result = {"question_id": question_id, "answered": True}
        if record_as == "entity_dictionary" and entity_id:
            await self.update_entity_dictionary(
                entity_id=entity_id,
                note=f"(from Q{question_id}) {answer}",
                source="user",
                confidence=1.0,
            )
            result["also_recorded_in"] = "entity_dictionary"
        elif record_as == "preference":
            await self.record_preference(key=question_id, value=answer)
            result["also_recorded_in"] = "preferences"
        else:
            await self.record_observation(
                topic=target["question"][:60],
                claim=answer,
                evidence=f"User answered {question_id}",
                source="user",
                confidence=1.0,
            )
            result["also_recorded_in"] = "observations"
        log.info("knowledge.question_answered", id=question_id, record_as=record_as)
        return result

    # ---------- 안전 경계 ----------
    async def request_approval(self, action: str, reason: str) -> dict[str, Any]:
        log.warning("APPROVAL_REQUESTED", action=action, reason=reason)
        print(f"\n⚠️  APPROVAL: {action}\n   reason: {reason}\n   [Phase 1: auto-approved]\n")
        await asyncio.sleep(0)
        return {"approved": True, "channel": "stub"}

    # ---------- Dispatcher ----------
    async def dispatch(self, name: str, arguments: dict[str, Any]) -> Any:
        method = getattr(self, name, None)
        if method is None or not callable(method):
            raise ValueError(f"Unknown tool: {name}")
        return await method(**arguments)

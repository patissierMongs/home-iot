"""
home-iot Analyst Chat — conversational data analysis powered by local LLM.

Architecture:
  Browser (Plotly.js + vanilla JS)
    <-> WebSocket
  FastAPI (:8501)
    <-> Ollama API (tool-calling loop)
  InfluxDB / HA API (via tools)

Key design decision: the LLM does NOT generate Plotly JSON directly.
Instead, it calls a `create_chart` tool with structured parameters (chart_type,
x/y arrays, labels). The tool returns a clean Plotly spec. This avoids the
"LLM embeds broken JSON in markdown" problem entirely.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Add agent src to path so we can reuse tools/llm/config
agent_src = str(Path(__file__).resolve().parent.parent / "agent" / "src")
if agent_src not in sys.path:
    sys.path.insert(0, agent_src)

from home_iot.config import settings  # noqa: E402
from home_iot.ha import HAClient  # noqa: E402
from home_iot.tools import Tools, TOOL_SCHEMAS  # noqa: E402
from home_iot.llm import LLM  # noqa: E402

app = FastAPI(title="home-iot Analyst Chat")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Shared instances
ha: HAClient | None = None
tools: AnalystTools | None = None  # type: ignore
llm: LLM | None = None

# ---- Chart tool (the key innovation) ----

CHART_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_chart",
        "description": (
            "Create a Plotly chart to visualize data. Call this INSTEAD of embedding JSON in your text. "
            "The chart will be rendered alongside your text response automatically. "
            "Provide raw data arrays (x, y) and labels. For scatter, line, bar, box charts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "description": "One of: scatter, line, bar, box, heatmap",
                },
                "title": {"type": "string", "description": "Chart title (Korean OK)"},
                "x": {
                    "type": "array",
                    "items": {},
                    "description": "X-axis data array (numbers, strings, or dates)",
                },
                "y": {
                    "type": "array",
                    "items": {},
                    "description": "Y-axis data array (numbers)",
                },
                "x_label": {"type": "string", "description": "X-axis label"},
                "y_label": {"type": "string", "description": "Y-axis label"},
                "series_name": {"type": "string", "description": "Legend name for this series", "default": "data"},
                "x2": {"type": "array", "items": {}, "description": "Optional second series X data"},
                "y2": {"type": "array", "items": {}, "description": "Optional second series Y data"},
                "series2_name": {"type": "string", "description": "Second series legend name"},
                "series2_type": {"type": "string", "description": "Second series chart type (scatter/line/bar)"},
            },
            "required": ["chart_type", "title", "x", "y"],
        },
    },
}


def _build_plotly_spec(params: dict[str, Any]) -> dict[str, Any]:
    """Convert create_chart parameters to a Plotly.js spec."""
    chart_type = params.get("chart_type", "scatter")
    mode_map = {"scatter": "markers", "line": "lines+markers", "bar": None, "box": None}
    trace_type = "bar" if chart_type == "bar" else ("box" if chart_type == "box" else "scatter")

    trace1: dict[str, Any] = {
        "x": params["x"],
        "y": params["y"],
        "type": trace_type,
        "name": params.get("series_name", "data"),
    }
    if chart_type in mode_map and mode_map[chart_type]:
        trace1["mode"] = mode_map[chart_type]
    if chart_type == "scatter":
        trace1["marker"] = {"size": 8, "opacity": 0.7}

    traces = [trace1]

    # Optional second series
    if params.get("x2") and params.get("y2"):
        t2_type = params.get("series2_type", chart_type)
        trace2: dict[str, Any] = {
            "x": params["x2"],
            "y": params["y2"],
            "type": "bar" if t2_type == "bar" else "scatter",
            "name": params.get("series2_name", "series 2"),
        }
        if t2_type in ("line", "scatter"):
            trace2["mode"] = mode_map.get(t2_type, "markers")
        if t2_type != chart_type:
            trace2["yaxis"] = "y2"
        traces.append(trace2)

    layout: dict[str, Any] = {
        "title": params.get("title", ""),
        "xaxis": {"title": params.get("x_label", "")},
        "yaxis": {"title": params.get("y_label", "")},
    }
    if len(traces) > 1 and traces[1].get("yaxis") == "y2":
        layout["yaxis2"] = {
            "title": params.get("series2_name", ""),
            "overlaying": "y",
            "side": "right",
        }

    return {"data": traces, "layout": layout}


class AnalystTools(Tools):
    """Extends the base Tools with visualization tools for the analyst UI."""

    def __init__(self, ha: HAClient):
        super().__init__(ha)
        self._last_chart: dict | None = None
        self._last_map: dict | None = None
        self._last_timeline: dict | None = None

    async def create_chart(self, **kwargs) -> dict[str, Any]:
        spec = _build_plotly_spec(kwargs)
        self._last_chart = spec
        return {"status": "chart_created", "title": kwargs.get("title", ""), "points": len(kwargs.get("x", []))}

    async def create_map(self, **kwargs) -> dict[str, Any]:
        self._last_map = kwargs
        n_markers = len(kwargs.get("markers", []))
        n_path = len(kwargs.get("path", []))
        n_heat = len(kwargs.get("heatmap", []))
        return {"status": "map_created", "markers": n_markers, "path_points": n_path, "heatmap_points": n_heat}

    async def create_timeline(self, **kwargs) -> dict[str, Any]:
        self._last_timeline = kwargs
        return {"status": "timeline_created", "events": len(kwargs.get("events", []))}

    def pop_visuals(self) -> tuple[dict | None, dict | None, dict | None]:
        chart, mp, tl = self._last_chart, self._last_map, self._last_timeline
        self._last_chart = self._last_map = self._last_timeline = None
        return chart, mp, tl


MAP_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_map",
        "description": (
            "Show GPS locations on an interactive map (Leaflet + OpenStreetMap). Use for: "
            "showing visited places, travel routes, frequently visited locations, heatmaps. "
            "Provide markers (labeled points), path (GPS trail), and/or heatmap (density). "
            "The map renders alongside your text. Call ONCE per response."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "markers": {
                    "type": "array",
                    "description": "Array of labeled location pins",
                    "items": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"},
                            "lon": {"type": "number"},
                            "label": {"type": "string", "description": "Pin label (place name, etc.)"},
                            "detail": {"type": "string", "description": "Extra info shown in popup"},
                            "color": {"type": "string", "description": "CSS color, default blue"},
                        },
                        "required": ["lat", "lon"],
                    },
                },
                "path": {
                    "type": "array",
                    "description": "GPS breadcrumb trail (polyline). Array of {lat, lon} points in order.",
                    "items": {
                        "type": "object",
                        "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
                        "required": ["lat", "lon"],
                    },
                },
                "path_color": {"type": "string", "description": "Polyline color", "default": "#58a6ff"},
                "heatmap": {
                    "type": "array",
                    "description": "Density heatmap points. Array of {lat, lon, intensity}.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"},
                            "lon": {"type": "number"},
                            "intensity": {"type": "number", "description": "0-1 weight", "default": 1},
                        },
                        "required": ["lat", "lon"],
                    },
                },
                "center": {
                    "type": "array",
                    "description": "[lat, lon] map center. Auto-calculated from data if omitted.",
                    "items": {"type": "number"},
                },
                "zoom": {"type": "integer", "description": "Map zoom level (1-18)", "default": 13},
                "title": {"type": "string", "description": "Title shown above map"},
            },
        },
    },
}

TIMELINE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_timeline",
        "description": (
            "Show a vertical timeline of events (visits, activities, movements). "
            "Each event has a time, label, type (VISIT/WALKING/IN_VEHICLE/CYCLING/STILL), "
            "and optional duration. Renders as a styled vertical timeline."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "description": "Timeline events in chronological order",
                    "items": {
                        "type": "object",
                        "properties": {
                            "time": {"type": "string", "description": "Time string (e.g. '09:30', '2026-04-06 14:00')"},
                            "label": {"type": "string", "description": "Event description"},
                            "type": {"type": "string", "description": "VISIT, WALKING, IN_VEHICLE, CYCLING, STILL, etc."},
                            "duration_min": {"type": "number", "description": "Duration in minutes"},
                        },
                        "required": ["time", "label"],
                    },
                },
                "title": {"type": "string", "description": "Timeline title"},
            },
            "required": ["events"],
        },
    },
}

# Build the combined tool schemas
ANALYST_TOOL_SCHEMAS = TOOL_SCHEMAS + [CHART_TOOL_SCHEMA, MAP_TOOL_SCHEMA, TIMELINE_TOOL_SCHEMA]


ANALYST_SYSTEM_PROMPT = """\
You are a data analyst for a smart home. The user asks questions in Korean about their
life data (sleep, heart rate, stress, activity, environment). Answer in Korean.

## Available data in InfluxDB (bucket: home-iot)

### Samsung Health (2018-2026, 8 years)
- `samsung_hr` — field: bpm. ~8000 points.
- `samsung_sleep_stage` — tag: stage (awake/light/deep/rem), field: stage_code/marker. ~33000 points.
- `samsung_sleep` — field: duration_min, efficiency, quality. ~900 sessions.
- `samsung_stress` — field: score (0-100). ~5700 points.
- `samsung_spo2` — field: spo2. ~480 points.
- `samsung_steps` — field: count, distance_m, calories. ~4400 daily records.
- `samsung_exercise` — field: duration_ms, calories, distance_m. tag: exercise_type. ~2500 sessions.

### Sleep as Android (1 year, 437 sessions)
- `sleep_session` — field: hours, deep_sleep, cycles, snore, noise.

### Home Environment (recent months via HA sensors)
- Measurement = unit of measurement, entity_id = tag (without domain prefix)
- `°C` + entity_id: keompyuteo_onseubdo_temperature, cimdaeonseubdo_temperature, hwajangsil_onseubdo_temperature
- `%` + entity_id: *_humidity, yuyu_cpuload_2, yuyu_gpuload_2
- `lx`: illuminance sensors
- `W`: jeseubgi_power (dehumidifier)

### Google Timeline (2024-07 ~ present, 50K points)
- `timeline_visit` — field: place_id, probability, duration_min, latitude, longitude. Tag: semantic_type
- `timeline_activity` — field: distance_m, duration_min, start_lat/lon, end_lat/lon. Tag: activity_type (WALKING/IN_VEHICLE/CYCLING)
- `timeline_gps` — field: latitude, longitude. Dense GPS breadcrumbs (45K points)
- `gfit_location` — field: latitude, longitude, accuracy_m. Google Fit GPS (11K, 2016-2020)

### Google Takeout
- `gfit_daily` — field: calories, distance_m, steps, hr_avg/max/min, speed_avg. 15-min intervals, 2014-2026.
- `chrome_history` — field: title, url, visit. Tag: domain. 76K entries.
- `calendar_event` — field: summary, event. Tag: calendar.
- `saved_place` — field: latitude, longitude, address. 52 user-saved locations.

### System (Telegraf): nvidia_smi, cpu, mem, docker_container_cpu

## How to work

1. Call `get_home_context()` if you need home layout/habits knowledge.
2. Use `query_influx()`, `get_sleep_stats()`, `get_activity_summary()`, etc. to get REAL data.
3. Compute statistics (correlations, trends) from the tool results.
4. Write your analysis in Korean.
5. **To show a chart**, call `create_chart` with chart_type, x/y arrays, title, labels.
6. **To show locations on a map**, call `create_map` with markers (pins), path (GPS trail), or heatmap (density).
   - For visited places: use markers [{lat, lon, label, detail}]
   - For travel routes: use path [{lat, lon}, ...]
   - For frequently visited areas: use heatmap [{lat, lon, intensity}]
7. **To show a timeline of events**, call `create_timeline` with events [{time, label, type, duration_min}].
   - Types: VISIT, WALKING, IN_VEHICLE, CYCLING, STILL
8. Do NOT embed JSON or code blocks in your text. The tools handle all rendering.
9. After calling a visualization tool, describe what it shows in your text.
10. You can call at most ONE of each (chart, map, timeline) per response.

## Important
- NEVER fabricate data. Always query first.
- For correlations, compute Pearson r and state the value.
- Keep text concise but insightful.
- Call create_chart at most once per response (the most important visualization).
"""


@app.on_event("startup")
async def startup():
    global ha, tools, llm
    ha = HAClient()
    tools = AnalystTools(ha)
    # Custom LLM that uses the extended tool schemas
    llm = LLM.__new__(LLM)
    llm.tools = tools
    llm.model = settings.ollama_main_model
    llm.thinking = True
    llm._http = __import__("httpx").AsyncClient(base_url=settings.ollama_url, timeout=180.0)


@app.on_event("shutdown")
async def shutdown():
    if ha:
        await ha.aclose()
    if llm and hasattr(llm, "_http"):
        await llm._http.aclose()


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            user_msg = await ws.receive_text()
            await ws.send_json({"type": "status", "status": "thinking"})

            try:
                reply = await _analyst_chat(user_msg)
                chart, map_spec, timeline = tools.pop_visuals()
                await ws.send_json({"type": "answer", "text": reply, "chart": chart, "map": map_spec, "timeline": timeline})
            except Exception as e:
                import traceback
                traceback.print_exc()
                await ws.send_json({"type": "error", "text": f"Error: {e}"})
    except WebSocketDisconnect:
        pass


async def _analyst_chat(user_msg: str) -> str:
    """Run the analyst LLM with extended tool schemas including create_chart."""
    import httpx

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    for iteration in range(15):
        payload = {
            "model": llm.model,
            "messages": messages,
            "stream": False,
            "tools": ANALYST_TOOL_SCHEMAS,
            "options": {"thinking": True} if llm.thinking else {},
        }
        resp = await llm._http.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        msg = data["message"]

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return msg.get("content", "")

        messages.append(msg)
        for call in tool_calls:
            fn = call["function"]
            name = fn["name"]
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            try:
                result = await tools.dispatch(name, args)
            except Exception as e:
                result = {"error": str(e)}
            messages.append({
                "role": "tool",
                "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    return "[최대 반복 횟수 도달]"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8501)

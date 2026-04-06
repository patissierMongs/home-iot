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
    """Extends the base Tools with create_chart for the analyst UI."""

    def __init__(self, ha: HAClient):
        super().__init__(ha)
        self._last_chart: dict | None = None

    async def create_chart(self, **kwargs) -> dict[str, Any]:
        spec = _build_plotly_spec(kwargs)
        self._last_chart = spec
        return {"status": "chart_created", "title": kwargs.get("title", ""), "points": len(kwargs.get("x", []))}

    def pop_chart(self) -> dict | None:
        c = self._last_chart
        self._last_chart = None
        return c


# Build the combined tool schemas
ANALYST_TOOL_SCHEMAS = TOOL_SCHEMAS + [CHART_TOOL_SCHEMA]


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

### System (Telegraf): nvidia_smi, cpu, mem, docker_container_cpu

## How to work

1. Call `get_home_context()` if you need home layout/habits knowledge.
2. Use `query_influx()`, `get_sleep_stats()`, `get_activity_summary()`, etc. to get REAL data.
3. Compute statistics (correlations, trends) from the tool results.
4. Write your analysis in Korean.
5. **To show a chart, call the `create_chart` tool** with chart_type, x/y arrays, title, labels.
   Do NOT embed JSON or code blocks in your text. The chart tool handles rendering.
6. After calling create_chart, just describe what the chart shows in your text.

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
                # Override tool schemas for this LLM call
                reply = await _analyst_chat(user_msg)
                chart = tools.pop_chart()
                await ws.send_json({"type": "answer", "text": reply, "chart": chart})
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

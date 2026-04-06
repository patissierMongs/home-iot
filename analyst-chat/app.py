"""
home-iot Analyst Chat — conversational data analysis powered by local LLM.

Architecture:
  Browser (Plotly.js + vanilla JS)
    ↕ WebSocket
  FastAPI (:8501)
    ↕ Ollama API (tool-calling loop)
  InfluxDB / HA API (via tools)

The LLM receives a system prompt that tells it to:
  1. Always respond with a JSON block containing "text" (Korean analysis) and optional "chart" (Plotly spec)
  2. Use tools to query real data before answering
  3. Compute correlations, trends, anomalies in Python (via the tool results)
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
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
from home_iot.tools import Tools  # noqa: E402
from home_iot.llm import LLM  # noqa: E402

app = FastAPI(title="home-iot Analyst Chat")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# Shared instances (created on startup)
ha: HAClient | None = None
tools: Tools | None = None
llm: LLM | None = None

ANALYST_SYSTEM_PROMPT = """\
You are a data analyst for a smart home. The user asks questions about their life data
(sleep, heart rate, stress, activity, environment, etc.) stored in InfluxDB.

## Available data in InfluxDB (bucket: home-iot)

### Samsung Health (8 years of history, 2018-2026)
- `samsung_hr` — field: bpm, bpm_min, bpm_max. Tag: source=samsung_health
- `samsung_sleep_stage` — field: stage_code, marker. Tag: stage (awake/light/deep/rem)
- `samsung_sleep` — field: duration_min, efficiency, quality
- `samsung_stress` — field: score (0-100)
- `samsung_spo2` — field: spo2
- `samsung_steps` — field: count, distance_m, calories
- `samsung_exercise` — field: duration_ms, calories, distance_m, mean_hr. Tag: exercise_type
- `samsung_com` — generic catch-all for skin_temperature, vitality_score, floors, etc.

### Sleep as Android (1 year)
- `sleep_session` — field: hours, deep_sleep, cycles, snore, noise. Tag: session_id
- `sleep_actigraphy` — field: activity (5-min intervals)

### Home Environment (HA sensors, recent months)
- `°C` measurement, entity_id tag: keompyuteo_onseubdo_temperature, cimdaeonseubdo_temperature, hwajangsil_onseubdo_temperature, etc.
- `%` measurement, entity_id tag: *_humidity sensors, yuyu_cpuload_2, yuyu_gpuload_2, yuyu_memoryusage_2
- `lx` measurement: illuminance sensors
- `W` measurement: jeseubgi_power (dehumidifier)

### ActivityWatch (recent)
- `activity_window` — field: title, duration_s. Tag: app, host
- `activity_afk` — field: duration_s. Tag: status (afk/not-afk)

### System (Telegraf)
- `nvidia_smi` — field: utilization_gpu, temperature_gpu, memory_used
- `cpu`, `mem`, `disk`, `docker_container_cpu`, etc.

## Response format

Your ENTIRE response must be a single JSON object. No text outside the JSON.
Do NOT wrap the JSON in markdown code blocks (no ```).
Do NOT use Python syntax inside JSON (no list comprehensions, no f-strings).

{
  "text": "Korean analysis text. Use **bold** and ## headers for formatting.",
  "chart": {
    "data": [{"x": [1,2,3], "y": [4,5,6], "type": "scatter", "name": "label"}],
    "layout": {"title": "Chart title", "xaxis": {"title": "X"}, "yaxis": {"title": "Y"}}
  }
}

If no chart is needed, set "chart": null.

CRITICAL RULES for the chart field:
- All arrays must be literal JSON arrays with actual numbers, NOT Python expressions
- WRONG: "size": [ (1 + s*0.5) for s in [...] ]
- CORRECT: "size": [3.67, 4.49, 2.77, ...]
- Chart types: scatter (correlations), scatter+mode:lines (trends), bar (comparisons)
- Keep data arrays under 200 points — aggregate if needed

## Analysis principles
- Always query real data via tools before answering. Never make up numbers.
- Compute Pearson correlation when asked about relationships (r value + interpretation).
- Use get_home_context() first to understand the home layout and known patterns.
- For sleep analysis, use get_sleep_stats() which does proper daily aggregation.
- For Samsung Health queries, use query_influx() with the correct measurement names above.
- When data is insufficient, say so honestly.
- Respond in Korean for text, English for chart labels.
"""


@app.on_event("startup")
async def startup():
    global ha, tools, llm
    ha = HAClient()
    tools = Tools(ha)
    llm = LLM(tools, model=settings.ollama_main_model, thinking=True)


@app.on_event("shutdown")
async def shutdown():
    if ha:
        await ha.aclose()
    if llm:
        await llm.aclose()


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            user_msg = await ws.receive_text()
            # Send "thinking" status
            await ws.send_json({"type": "status", "status": "thinking"})

            try:
                reply = await llm.chat(
                    ANALYST_SYSTEM_PROMPT,
                    user_msg,
                    max_iterations=15,
                )
                # Try to parse as JSON
                parsed = _extract_json(reply)
                if parsed:
                    await ws.send_json({"type": "answer", **parsed})
                else:
                    await ws.send_json({"type": "answer", "text": reply, "chart": None})
            except Exception as e:
                await ws.send_json({"type": "error", "text": f"Error: {e}"})
    except WebSocketDisconnect:
        pass


def _extract_json(text: str) -> dict | None:
    """
    Robustly extract text + chart from LLM response.

    LLMs often don't return clean JSON. Common patterns:
    1. Clean JSON: {"text": "...", "chart": {...}}
    2. Text with embedded ```json chart spec ``` code block
    3. Text with Python syntax in JSON (list comprehensions, etc.)
    4. Just plain text with no chart
    """
    import re

    # 1. Try direct JSON parse
    try:
        d = json.loads(text)
        if isinstance(d, dict) and "text" in d:
            return d
    except json.JSONDecodeError:
        pass

    # 2. Try to find a {"text": ..., "chart": ...} JSON block
    m = re.search(r'(\{"text"\s*:.*\})\s*$', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Split: extract chart from ```json...``` code block, rest is text
    chart = None
    clean_text = text

    # Find all ```json ... ``` blocks — take the biggest one as chart candidate
    json_blocks = re.findall(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    for block in sorted(json_blocks, key=len, reverse=True):
        # Clean Python syntax from JSON (list comprehensions, etc.)
        cleaned = _clean_python_in_json(block)
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and ("data" in parsed or "layout" in parsed):
                chart = parsed
                # Remove the code block from text
                clean_text = text[:text.find(block) - 10]  # rough removal
                clean_text = re.sub(r'```(?:json)?\s*\{[\s\S]*?\}\s*```', '', clean_text).strip()
                break
        except json.JSONDecodeError:
            continue

    # If we found a chart, return structured response
    if chart:
        # Clean up remaining markdown artifacts in text
        clean_text = re.sub(r'```\s*```', '', clean_text).strip()
        return {"text": clean_text, "chart": chart}

    # 4. No chart found — return as plain text
    return None


def _clean_python_in_json(text: str) -> str:
    """Remove Python expressions that LLMs sometimes embed in JSON."""
    import re
    # Remove list comprehensions: [ expr for var in [...] ]
    # Replace with the source list if detectable
    def replace_listcomp(m):
        # Try to extract the source list
        inner = m.group(0)
        source_match = re.search(r'for\s+\w+\s+in\s+(\[[\d.,\s]+\])', inner)
        if source_match:
            return source_match.group(1)
        return "[]"

    text = re.sub(r'\[\s*\(.*?\)\s+for\s+\w+\s+in\s+\[.*?\]\s*\]', replace_listcomp, text, flags=re.DOTALL)
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8501)

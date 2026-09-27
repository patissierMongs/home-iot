# Progress record

**English** | [한국어](PROGRESS.md)

## Final goal

Build a smart home hub that gathers home devices (HA (Home Assistant) integrations, sensors, PCs) and personal activity data (sleep, health, location, PC usage) on a local server, and that:

1. Handles well-defined situations immediately with deterministic rules.
2. Lets a local LLM (Large Language Model) agent judge ambiguous situations through tool calls, asking the user for approval before sensitive actions.
3. Accumulates what the agent learns about the home and its occupant in a YAML (YAML Ain't Markup Language) knowledge base, and presents the collected data through conversational analysis and dashboards.

## Current implementation status

Verified by reading the code on 2026-09-27. Status is one of Implemented, Partial or Not started. The repository has no automated tests.

| Feature | Status | Code location checked | Notes |
|---|---|---|---|
| Docker Compose stack (HA, Mosquitto, InfluxDB, Grafana, Ollama, Telegraf) | Implemented | `stack/docker-compose.yml`, `stack/telegraf/telegraf.conf`, `stack/mosquitto/config/mosquitto.conf` | Mosquitto allows anonymous access (development setting). |
| HA REST (Representational State Transfer) and WebSocket client | Implemented | `agent/src/home_iot/ha.py` | State reads, service calls, event stream with reconnect |
| Agent event loop (rules → LLM) | Implemented | `agent/src/home_iot/agent.py` | Sends `binary_sensor.`, `person.` and `device_tracker.` state changes to the LLM. |
| Deterministic rule engine | Partial | `agent/src/home_iot/rules.py` | The engine exists, but `DEFAULT_RULES` is empty and `Agent` registers no rules. |
| Ollama tool-calling adapter | Implemented | `agent/src/home_iot/llm.py` | |
| 17 agent tools | Implemented | `agent/src/home_iot/tools.py` (`TOOL_SCHEMAS`, `Tools`) | HA, InfluxDB, sleep, activity, places, 7 knowledge tools, approval request |
| Place reverse geocoding (Nominatim) | Implemented | `agent/src/home_iot/tools.py` `_reverse_geocode` | |
| User approval request | Partial | `agent/src/home_iot/tools.py` `request_approval` | Stub that logs and always auto-approves. |
| YAML knowledge base (layout, knowledge, question queue) | Implemented | `agent/config/*.example.yaml`; `get_home_context`, `record_*`, `answer_question` in `tools.py` | Real files are gitignored. |
| Exposing tools as an MCP (Model Context Protocol) server | Not started | Only mentioned as a plan in `tools.py` comments. | |
| ActivityWatch bridge | Implemented | `agent/src/home_iot/bridges/activitywatch.py` | Runs inside the agent. |
| Qingping air monitor bridge | Partial | `agent/src/home_iot/bridges/qingping.py` | Has a polling loop (`run`), but the standalone `main` polls once and exits; not wired into the agent. |
| Samsung Health importer | Implemented | `agent/src/home_iot/importers/samsung_health.py`, `agent/scripts/import_samsung_health.py` | |
| Sleep as Android importer | Implemented | `agent/src/home_iot/importers/sleep_as_android.py`, `agent/scripts/import_sleep_as_android.py` | |
| Google Takeout importer (Fit, Chrome, Calendar, saved places) | Implemented | `agent/scripts/import_google_takeout.py` | |
| Google Timeline (`timeline_visit`, `timeline_gps`) importer | Not started | Tools and analytics read these measurements, but no code in the repository writes them. | |
| Integrated analytics engine | Implemented | `agent/src/home_iot/analytics.py`, `agent/scripts/refresh_analytics.py` | Writes `analytics_*` measurements. |
| 7 Grafana dashboards and provisioning | Implemented | `stack/grafana/dashboards/*.json`, `stack/grafana/provisioning/` | Not loaded in a running Grafana during this review. |
| Weekly review (Anthropic API) | Implemented | `agent/scripts/weekly_review.py` | Supports `--dry-run` |
| Analyst chat web UI (User Interface) | Implemented | `analyst-chat/app.py`, `analyst-chat/static/index.html` | 7 visualization tools. Run with a stub LLM to confirm the screen. |
| Life Explorer HTML (HyperText Markup Language) generator | Partial | `dashboards/life-explorer.py`, `dashboards/build_explorer_v3.py`, `dashboards/explorer_template.html` | The collection script that produces the input JSON (JavaScript Object Notation) is missing, and nothing fills `explorer_template.html`. |
| Desktop audio player (MQTT (Message Queuing Telemetry Transport) → TTS (Text-to-Speech)) | Implemented | `desktop-audio-player/audio_player.py`, `desktop-audio-player/start.ps1` | Windows only |
| Early custom MQTT bridge (Hue) | Implemented | `reference/` | Legacy code, no longer used. |

## Work history

Derived from `git log`. The stored commit offsets are already +09:00, so times are shown as KST (Korea Standard Time) as-is.

| Date (KST) | Commit | Change |
|---|---|---|
| 2026-04-06 13:27 | 92843c0 | Initial release: Docker stack, agent, analyst chat |
| 2026-04-06 13:42 | 3c6b41c | Analyst chat uses a `create_chart` tool instead of LLM-generated JSON |
| 2026-04-06 16:37 | 2c73169 | Add weekly review script |
| 2026-04-06 21:06 | 7178dce | Add Google Takeout importer |
| 2026-04-06 21:22 | 8cc012f | Add map and timeline visualizations to analyst chat |
| 2026-04-06 21:50 – 22:31 | 263e9aa, 2dee77c, 8831d52, 2fe8fc1, c339b85 | Analyst chat prompt rework, 6 visualization types, timezone fix |
| 2026-04-06 22:36 | 3812bf8 | Add location analytics tools (17 tools) |
| 2026-04-06 22:41 | 2a6f0fb | Add Nominatim reverse geocoding for places |
| 2026-04-07 19:33 | ca0241f | Write project conventions into `CLAUDE.md` |
| 2026-04-07 19:37 | 7b956b7 | Fix 5 issues from code review |
| 2026-04-07 19:50 | 3f19539 | Add Gantt chart visualization |
| 2026-04-07 20:31 – 21:09 | f8bed10, 62450c2, edede67 | Life Explorer dashboard v1, v3 and the ORBITAL template |
| 2026-04-07 21:48 | abbcf9e | Add Qingping cloud API (Application Programming Interface) → MQTT bridge |
| 2026-04-07 21:57 | fb6ec62 | Add integrated analytics engine |
| 2026-04-07 22:01 | d5d7a27 | Add Grafana integrated analytics dashboard and refresh script |
| 2026-05-13 16:10 | 66b0d6d | Ignore the local virtualenv folder |
| 2026-09-27 | this work | Remove personal info, split README into Korean and English, add screenshots, write this progress record |

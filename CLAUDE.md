# home-iot — Claude working guide

This project has a **persistent knowledge base that accumulates through conversation and observation**. Any Claude session must use it to avoid re-asking the same questions and to carry learnings forward from previous sessions.

## 📚 Knowledge files

```
agent/config/
├── home_layout.yaml      user-edited — fixed layout / zones / habits / safety boundaries
├── home_knowledge.yaml   agent-accumulated — observations / facts / preferences / patterns / lessons
└── open_questions.yaml   pending question queue (the question text itself is Korean because it will be shown to the user)
```

## 🔄 Working protocol

### At session start
1. Read `agent/config/home_knowledge.yaml` and `agent/config/open_questions.yaml` **first** to understand current state.
2. If any open question fits the conversation context, raise it naturally — but only when the user isn't in the middle of another task.

### During the conversation
- **Unknown device/purpose/location** → ask the user → on answer, record immediately in `entity_dictionary`.
- **User mentions a preference/habit** → record it in `preferences`.
- **You discover a reusable fact during analysis/debugging** → append to `observations` (ids follow `O{NNN}` pattern, next increment).
- **Project operational mistake or lesson learned** → append to `lessons`.
- **Something you'd like to know but can't ask now** → add to `open_questions.yaml` as `Q{NNN}`.

### Write schema
```yaml
# entity_dictionary entry
<entity_id>:
  role: "..."            # device function
  location: "..."        # zone name
  note: "..."            # quirks
  confidence: 0.0-1.0
  source: user | observed | inferred | imported
  updated: YYYY-MM-DD

# observations entry
- id: O{NNN}
  date: YYYY-MM-DD
  topic: "short topic"
  claim: "observed fact"
  evidence: "basis / source"
  source: user | observed | inferred
  confidence: 0.0-1.0

# preferences entry
<key>:
  value: "..."
  source: user
  date: YYYY-MM-DD
```

### After every write
- Update `metadata.last_updated` to the current timestamp.
- No duplicate ids (use max existing + 1).

## ⛔ Do not
- Re-ask the user for information already in YAML.
- Let Claude write directly to `home_layout.yaml` (the user manages that one manually).
- Record a guess with `confidence: 1.0`.
- Store sensitive personal observations (browser history details, etc.) with full content — record only the category.

## 🤖 Relationship with the running agent

The Python agent under `agent/src/home_iot/` runs Ollama + Nemotron Cascade 2 and **reads/writes the same YAML files through the same tool interface** (7 of the 15 tools in `tools.py` are knowledge-related).

So anything this Claude session records is also seen by the next Claude session and by the 24/7 Nemotron agent. Single source of truth.

## 📂 Project structure overview

```
/home/yuyu/home-iot/
├── stack/               Docker Compose: HA, Mosquitto, InfluxDB, Grafana, Ollama, Telegraf
├── agent/               Python agent
│   ├── src/home_iot/    ha / tools / llm / rules / agent / bridges / importers
│   ├── config/          home_layout.yaml, home_knowledge.yaml, open_questions.yaml
│   └── scripts/         one-shot scripts (e.g., SaA importer)
└── reference/           legacy custom MQTT bridge code (learning reference, not used)
```

Higher-level context also lives at `~/.claude/projects/.../memory/project_home_iot.md`.

## Database Conventions

When working with InfluxDB, always verify the schema first — distinguish between fields and tags before writing queries or ingestion code. Never assume field/tag classifications. HA's InfluxDB integration uses `_measurement = unit_of_measurement` (e.g. `°C`, `%`, `lx`) with `entity_id` as a tag (without domain prefix). Custom measurements (sleep_session, samsung_hr, activity_window, timeline_visit, etc.) use their own schemas. Always check with a sample query before building dashboards or tools.

## Data Import / Parsing

When parsing CSV files (especially Samsung Health exports), validate against actual file headers and sample rows before writing the parser. Print the first 3 rows and confirm column names before proceeding. Samsung Health CSVs have a metadata line before the real header — skip line 0. Column names often have long prefixes like `com.samsung.health.heart_rate.heart_rate` — use substring matching, not exact key lookup.

## Environment

When working in WSL, always check if commands need sudo before running them. Avoid sudo for Docker commands if the user is in the docker group (already configured). The user has passwordless sudo via `/etc/sudoers.d/yuyu-nopasswd`. PowerShell cannot be called from this WSL instance (exec format error) — Windows-side commands must be done by the user or via SSH/HASS.Agent.

## Home Assistant / IoT

For Home Assistant integrations, always reference the exact enum values and entity naming conventions from the official docs or existing config — don't guess. Example: HASS.Agent sensor types use `AudioSensors` (plural, MultiValue) not `AudioSensor` (singular). Verify against source code enums when available. For HA InfluxDB queries, always check `_measurement` + `entity_id` tag + `_field` before building dashboard panels.

## 🗣 Language policy

- All LLM-consumed documents (this file, system prompts, tool descriptions, observation claims, lessons, English README-style content) — **English**.
- Direct chat with the user — **Korean**.
- `open_questions.yaml` question text — Korean (user-facing).
- Entity IDs and concrete Korean names — keep as-is.

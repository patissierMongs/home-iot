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

## 🗣 Language policy

- All LLM-consumed documents (this file, system prompts, tool descriptions, observation claims, lessons, English README-style content) — **English**.
- Direct chat with the user — **Korean**.
- `open_questions.yaml` question text — Korean (user-facing).
- Entity IDs and concrete Korean names — keep as-is.

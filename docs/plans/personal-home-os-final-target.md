# Personal Home OS Final Target and Implementation Plan

> **For Hermes:** Use `subagent-driven-development` only for larger future slices. For small code changes, continue strict TDD directly in this branch.

**Goal:** Build `home-iot` into a proactive Personal Home OS: Home Assistant is the source of truth for reality, while the agent reads HA states/events, builds life context, finds long-term personal patterns, speaks concise coaching, and adjusts the home through HA.

**Architecture:** Home Assistant owns device integrations, sensor fusion, template sensors, helpers, and low-level detection. The Python agent is a semantic reasoning layer above HA: it maps HA events into trusted life events, records an event ledger, builds `now.json`, plans routine actions, later speaks or executes them through HA service calls. The agent must not re-implement how hardware detects state.

**Tech Stack:** Python 3.12, Home Assistant REST/WebSocket API, YAML config contracts, JSONL event ledger, pytest, existing InfluxDB/Grafana/Ollama stack, future Garmin Connect/FIT ingestion, ActivityWatch summary sensors, ElevenLabs/edge-tts or HA media players for voice.

---

## 1. Core Product Vision

This project is not a generic IoT dashboard. The target is a 24/7 personal smart-home and health intelligence layer.

The final system should answer and act on questions like:

- What is the user's current state: recovery, sleep debt, stress, focus, activity, environment?
- What did the user already do today: workout, shower, supplements, computer work, bedtime routine?
- What should be nudged now, delayed, or avoided because the user is focusing/sleeping/in a meeting?
- Which home actions improve recovery, sleep, focus, and routine adherence?
- Which long-term patterns are personally validated for this user?

The long-term product is a proactive cohabitant-style agent:

```text
HA state/events + health/activity/lifestyle history
  → daily context
  → deterministic safety/routine rules
  → LLM judgment and natural language coaching
  → HA service calls / speaker / reminders
  → event journal and analytics feedback loop
```

## 2. Non-Negotiable Architecture Rule

Home Assistant is the central source of truth.

The agent must not decide whether a bottle was lifted, whether a shower happened, whether a person is home, or whether a light is actually on by inspecting raw hardware signals. That belongs in HA integrations, ESPHome, template sensors, helpers, automations, or vendor integrations.

The agent only consumes HA-level facts:

```text
binary_sensor.supplement_magnesium_present = off
input_boolean.supplement_magnesium_taken_today = on
binary_sensor.shower_done_today = on
sensor.computer_current_mode = coding
sensor.garmin_body_battery = 31
sensor.bedroom_co2 = 910
```

Then it maps those facts to life meaning:

```text
supplement.taken.magnesium
routine.done.shower
computer.focus_block
night_routine.take_magnesium
night_routine.ventilate_bedroom
```

## 3. Current Branch State

Branch:

```text
feat/personal-home-os-ha-agent
```

Baseline before redesign:

```text
stable-before-personal-home-os
66b0d6d chore: ignore local virtualenv
```

Implemented commits so far:

```text
ddba883 feat: add night routine action planner
bf83051 feat: build current context from HA state
248688c feat: wire semantic events into agent loop
9a47b40 feat: add HA semantic event foundation
66b0d6d stable-before-personal-home-os baseline
```

Current verification at last checkpoint:

```bash
cd /home/yuyu/home-iot/agent
uv run pytest -q
# 15 passed

uv run python -m compileall -q src
# PASS
```

## 4. Implemented Foundation

### 4.1 Entity Contract

File:

```text
agent/config/entity_contract.yaml
```

Purpose:

- Defines the HA entities the agent is allowed to depend on.
- Prevents hard-coded entity IDs from spreading through agent logic.
- Keeps HA as source of truth while giving the agent a stable interface.

Current domains:

```text
health
environment
actuators
presence
computer
routines
supplements
```

### 4.2 Semantic Entity Mapping

File:

```text
agent/config/semantic_entities.yaml
```

Purpose:

- Maps trusted HA `state_changed` transitions to semantic events.
- Example: supplement presence `on → off` means taken.

Current examples:

```text
binary_sensor.supplement_magnesium_present on→off
  → supplement.taken.magnesium

binary_sensor.user_home off→on
  → presence.arrived_home

binary_sensor.user_home on→off
  → presence.left_home

binary_sensor.shower_done_today off→on
  → routine.done.shower
```

### 4.3 Semantic Events and Ledger

Files:

```text
agent/src/home_iot/events.py
agent/src/home_iot/semantic.py
```

Purpose:

- Represent trusted life-domain events as `SemanticEvent`.
- Append events to JSONL files by date.

Output:

```text
agent/data/events/YYYY-MM-DD.jsonl
```

Example event:

```json
{
  "ts": "2026-05-13T22:11:04+09:00",
  "domain": "supplement",
  "type": "taken",
  "entity": "magnesium",
  "source": "home_assistant",
  "source_entity": "binary_sensor.supplement_magnesium_present",
  "old_state": "on",
  "new_state": "off",
  "trusted": true
}
```

### 4.4 Semantic Runtime in Agent Loop

Files:

```text
agent/src/home_iot/semantic_runtime.py
agent/src/home_iot/agent.py
```

Current flow:

```text
HA state_changed event
  → SemanticEventRuntime.handle_ha_event()
  → SemanticEventMapper.map_state_changed()
  → EventLedger.record()
  → optional HA helper update
  → ContextBuilder.build_now()
  → existing RuleEngine / LLM path
```

For supplements, semantic runtime currently updates HA helpers after recording the semantic event:

```text
input_boolean.supplement_magnesium_taken_today = on
input_datetime.supplement_magnesium_last_taken = event time
```

### 4.5 Context Builder

File:

```text
agent/src/home_iot/context.py
```

Output:

```text
agent/data/context/now.json
```

Purpose:

- Read HA states declared in `entity_contract.yaml`.
- Read today's semantic events from the JSONL ledger.
- Build a compact context object for deterministic routines and future LLM prompts.

Current sections:

```text
health
environment
computer
presence
routines
supplements
events_today
recommended_actions
```

### 4.6 Night Routine Planner

Files:

```text
agent/src/home_iot/routines/__init__.py
agent/src/home_iot/routines/night.py
```

Purpose:

- Deterministically produce `recommended_actions` from `now.json`.
- Keep this non-LLM and safe.

Current action candidates:

```text
take_magnesium
ventilate_bedroom
dim_lights_for_bedtime
```

Current deferral rules:

```text
computer.in_meeting == on
  → do not interrupt

computer.current_mode == coding and focus_block_minutes >= 45
  → defer low-priority night routine actions

night_briefing_done == on
  → skip

outside 21:00-23:59
  → skip
```

Example `recommended_actions`:

```json
[
  {
    "id": "take_magnesium",
    "priority": "medium",
    "message": "마그네슘 아직 안 챙기셨어요."
  },
  {
    "id": "ventilate_bedroom",
    "priority": "medium",
    "message": "침실 CO2가 940ppm이라 10분 환기 추천드려요."
  },
  {
    "id": "dim_lights_for_bedtime",
    "priority": "low",
    "message": "취침 준비를 위해 침실 조명을 낮춰둘게요.",
    "ha_service": {
      "domain": "light",
      "service": "turn_on",
      "target": {"entity_id": "light.bedroom"},
      "data": {"brightness_pct": 30}
    }
  }
]
```

### 4.7 Runtime Documentation

File:

```text
docs/agent-runtime.md
```

Purpose:

- Documents the HA-centered runtime principle.
- Documents semantic events, `now.json`, config files, and current MVP behavior.

## 5. Immediate Product Target

The first complete end-to-end slice should be:

```text
HA supplement/health/environment/computer state
  → trusted semantic event ledger
  → now.json
  → recommended_actions
  → briefing text
  → user-facing output via speaker or logs
  → optional HA action execution after safety policy
```

The MVP should feel like this:

```text
22:30
HA says:
  magnesium missing
  bedroom CO2 940
  computer mode video
  not in meeting
  not in focus block

Agent writes now.json:
  recommended_actions:
    - take_magnesium
    - ventilate_bedroom
    - dim_lights_for_bedtime

Agent briefing:
  "마그네슘 아직 안 챙기셨어요. 침실 CO2가 높아서 10분 환기 추천드려요.
   취침 준비를 위해 조명을 낮춰둘게요."

Later:
  speak briefing through desktop speaker or HA media_player
  execute safe HA actions if allowed
```

## 6. Final Target Capabilities

### 6.1 HA Entity Contract as Stable API

Final behavior:

- All agent dependencies on HA states live in `agent/config/entity_contract.yaml`.
- New sensors or renamed entities require config updates, not code rewrites.
- The agent can report missing/unavailable contract entities clearly.

Future entity categories:

```text
health: Garmin daily recovery/sleep/body metrics
activity: Garmin/FIT workout summary
computer: ActivityWatch machine summaries
nutrition: supplements, caffeine, hydration, food logs
routines: shower, bedtime, wake, workout recovery
calendar: next day constraints
actuators: lights, curtains, fans, purifier, speakers
```

### 6.2 Semantic Event Ledger

Final behavior:

- Every meaningful HA state transition becomes a trusted semantic event.
- Events are append-only and human-debuggable.
- InfluxDB write can be added later, but JSONL remains the simple source for LLM/debugging.

Candidate event domains:

```text
supplement.taken
presence.arrived_home
presence.left_home
routine.shower_done
routine.night_briefing_done
activity.workout_completed
computer.focus_started
computer.focus_ended
computer.late_screen_use
sleep.wake_detected
environment.ventilation_needed
action.spoken
action.ha_service_called
```

### 6.3 Context Builder

Final behavior:

- `agent/data/context/now.json` is always the compact, current state of the user's day.
- LLM prompts should read this instead of raw HA entities whenever possible.
- Context should be stable enough for dashboards, routines, and future chat UI.

Future sections:

```text
user_state
health
sleep
activity
environment
computer
nutrition
supplements
routines
calendar
recommended_actions
recent_agent_actions
open_questions
```

### 6.4 Routine Planners

Final behavior:

- Deterministic planners propose candidate actions.
- LLM may phrase, prioritize, or combine them, but deterministic planners own simple routine logic.
- Planners must be tested with pure input/output tests.

Planned modules:

```text
agent/src/home_iot/routines/night.py
agent/src/home_iot/routines/morning.py
agent/src/home_iot/routines/supplements.py
agent/src/home_iot/routines/recovery.py
agent/src/home_iot/routines/interruption.py
```

Initial scenarios:

1. Night Routine Coach
   - Supplements missing
   - Bedroom CO2 high
   - Screen use late at night
   - Body Battery low / workout today
   - Target bedtime adjustment

2. Morning Briefing
   - Sleep score
   - HRV / Body Battery
   - Bedroom overnight environment
   - First calendar constraint
   - Suggested work/exercise timing

3. Post-Workout Recovery
   - Workout completed
   - User arrived home
   - Shower not done
   - Protein/meal reminder
   - Bathroom light/fan/ventilation preparation via HA

4. Supplement Routine
   - HA helper says missing
   - Reminder window reached
   - Trusted taken event suppresses future reminder

### 6.5 Briefing Composer

Final behavior:

- Convert `recommended_actions` into short Korean user-facing text.
- Keep messages concise and practical.
- Avoid over-explaining sensor reasoning.

Example:

```text
마그네슘 아직 안 챙기셨어요. 침실 CO2가 940ppm이라 10분 환기 추천드려요.
취침 준비를 위해 조명은 낮춰둘게요.
```

Planned file:

```text
agent/src/home_iot/briefing.py
agent/tests/test_briefing.py
```

### 6.6 Action Executor

Final behavior:

- Execute only explicitly allowed safe actions automatically.
- High-risk actions require approval or remain recommendations only.
- All executed actions are recorded as semantic/action events.

Safe initial actions:

```text
light brightness/color temperature changes
fan/air purifier mode changes if already known safe
input_boolean/input_datetime helper updates
media_player TTS playback
```

Caution actions:

```text
curtain movement, because cover.keoteun state feedback is known unstable
fingerbot actions, because toggle devices need independent ground truth
large device power changes
anything involving locks/security
```

Planned file:

```text
agent/src/home_iot/action_executor.py
agent/tests/test_action_executor.py
```

### 6.7 Voice Output

Final behavior:

- The agent can speak selected briefings through the desktop speaker or HA media player.
- ElevenLabs is preferred if credentials are configured.
- edge-tts or HA native TTS can be fallback.
- Do not commit or document real API keys.

Planned files:

```text
agent/src/home_iot/voice/tts.py
agent/src/home_iot/voice/player.py
agent/tests/test_voice_tts.py
```

### 6.8 Garmin Integration

Final behavior:

Garmin should provide two layers of data:

1. Garmin Connect daily context:
   - sleep score
   - sleep stages
   - HRV status
   - Body Battery
   - stress
   - resting heart rate
   - steps
   - training readiness/status if available

2. FIT activity detail:
   - workout type
   - duration/distance
   - heart-rate zones
   - pace/cadence/laps
   - training effect
   - recovery time

Architecture rule:

```text
Garmin sync → HA sensors and/or InfluxDB → agent reads contract entities/context
```

The agent should not become a Garmin-specific reasoning island.

Planned files:

```text
agent/src/home_iot/bridges/garmin.py
agent/scripts/sync_garmin.py
agent/config/garmin.yaml.example
agent/tests/test_garmin_mapping.py
```

### 6.9 ActivityWatch Integration

Final behavior:

ActivityWatch should become a major routine/context source, but summarized through HA/contract entities where possible.

Desired HA-level outputs:

```text
sensor.computer_current_mode
sensor.computer_focus_block_minutes
sensor.computer_screen_after_22_minutes
sensor.computer_total_active_today_minutes
sensor.computer_context_switch_count_today
binary_sensor.computer_in_meeting
```

The agent should use these to decide:

- whether to interrupt now
- whether late screen use is affecting sleep
- whether the day was focus-heavy, fragmented, or recovery-heavy
- whether a routine reminder should be delayed

### 6.10 Long-Term Analytics / Golden Points

Final behavior:

Use collected events and health outcomes to discover personal patterns.

Examples:

```text
bedroom_co2 < 800 + target bedtime met → better sleep score
screen_after_22_minutes > 60 → longer sleep latency / lower HRV next day
zone2 workout day + magnesium taken → higher next-day Body Battery
late intense workout → delayed bedtime recommendation
```

Existing `analytics.py` should be reused where possible instead of building a parallel analysis stack.

## 7. Implementation Roadmap from Here

### Phase A: Briefing Text MVP

Goal:

```text
recommended_actions → concise Korean briefing text
```

Files:

```text
agent/src/home_iot/briefing.py
agent/tests/test_briefing.py
```

Acceptance:

- Pure function tests.
- No HA calls.
- No TTS yet.
- Handles empty action list.

### Phase B: Safe Action Executor MVP

Goal:

```text
recommended_actions with ha_service → safe HA service calls
```

Files:

```text
agent/src/home_iot/action_executor.py
agent/tests/test_action_executor.py
```

Acceptance:

- Only executes allowlisted action IDs/services.
- Records execution event or returns execution result.
- Does not execute curtain/fingerbot actions by default.

### Phase C: Agent Routine Tick

Goal:

```text
periodic or event-triggered routine tick reads now.json, composes briefing, optionally executes safe actions
```

Files:

```text
agent/src/home_iot/routine_runtime.py
agent/tests/test_routine_runtime.py
```

Acceptance:

- Test with fake HA and fake speaker.
- Does not double-speak if `night_briefing_done` is already on.
- Marks briefing done through HA helper only after successful output.

### Phase D: Voice Output

Goal:

```text
briefing text → desktop/HA speaker output
```

Files:

```text
agent/src/home_iot/voice/tts.py
agent/src/home_iot/voice/player.py
agent/tests/test_voice_tts.py
```

Acceptance:

- No real credentials in repo.
- Provider selected by config/env.
- Test provider returns deterministic fake audio path or fake HA media call.

### Phase E: ActivityWatch Contract Fulfillment

Goal:

```text
existing ActivityWatch bridge → HA/Influx summarized fields that match entity_contract.yaml
```

Files to inspect first:

```text
agent/src/home_iot/bridges/activitywatch.py
```

Acceptance:

- Multi-machine support plan.
- Current mode classification.
- Focus block and late-screen metrics.
- Tests for summary calculations.

### Phase F: Garmin Contract Fulfillment

Goal:

```text
Garmin Connect + FIT → HA/Influx health/activity entities
```

Acceptance:

- Credentials never committed.
- Daily health summary available to context builder.
- FIT files archived separately.
- Tests for mapping Garmin payloads to contract fields.

## 8. Testing Rules

Continue strict TDD.

For each code feature:

1. Write failing test.
2. Run the exact test and verify expected failure.
3. Implement minimal code.
4. Run targeted test.
5. Run full suite.
6. Compile check.
7. Commit.

Commands:

```bash
cd /home/yuyu/home-iot/agent
uv run pytest -q
uv run python -m compileall -q src
```

## 9. Safety and Scope Rules

- HA owns detection.
- Agent reads HA, writes semantic events, builds context, proposes actions.
- Agent acts only through HA service calls.
- Do not add direct Tuya/Hue/Qingping hardware control when HA already handles it.
- Do not model low-friction trusted events as uncertain unless user explicitly asks.
- Supplement presence `present on→off` is trusted as taken.
- Do not store credentials or API keys in docs, memory, summaries, tests, or commits.
- Avoid broad diagnostics/docs beyond what helps the current implementation.

## 10. Definition of Done for the First Real MVP

The first MVP is complete when this works end to end:

```text
1. HA has supplement, environment, computer, and routine entities.
2. A configured HA state transition occurs.
3. Agent records a semantic event to JSONL.
4. Agent updates HA helpers when configured.
5. Agent rebuilds now.json.
6. now.json contains recommended_actions.
7. Agent composes a Korean night briefing from those actions.
8. Agent outputs the briefing to a configured speaker or test sink.
9. Safe HA actions can be executed from allowlisted recommended_actions.
10. Tests pass and behavior is documented.
```

This is the smallest complete loop that proves the Personal Home OS direction:

```text
HA reality → semantic event → context → recommendation → user-facing coaching/action
```

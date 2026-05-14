# Personal Home OS Product and UI/UX Target

> **For Hermes:** Treat this as the product target for the Rust reboot in `personal-home-os/`. Do not continue expanding the old Python `agent/` except as a reference. Implement future features with TDD in the Rust crate.

**Goal:** Build a Home Assistant-centered personal operating system for the home: it observes trusted HA state/events, understands routines and health context, recommends or performs safe actions, and presents a calm dashboard/briefing UI that helps the user live better without adding manual tracking burden.

**Architecture:** Home Assistant remains the source of truth for sensors, hardware, helpers, and low-level automation. The Rust core consumes HA state/event streams, converts them into semantic events, builds `now.json` context, plans routines, composes briefings, and exposes a local web UI/API. Actuation always goes through HA service calls and a safety policy.

**Tech Stack:** Rust, Cargo, std/Tokio HTTP stack later, serde/serde_json/serde_yaml, reqwest, Home Assistant REST/WebSocket APIs, local JSONL event ledger, static server-rendered UI first, optional HTMX/SSE later, no frontend framework until needed.

---

## 1. Product North Star

Personal Home OS is not a generic smart-home dashboard.

It is a proactive personal home/health agent with a UI.

It should answer:

```text
What is going on with me and my home right now?
What should I do next?
What can the home quietly adjust for me?
What patterns are emerging over days/weeks?
```

The system should reduce friction, not create another app to maintain.

The ideal behavior:

```text
User lives normally
↓
Home Assistant records trusted state/events
↓
Rust core converts them into meaningful personal context
↓
UI shows current state, routines, and explanations
↓
Agent suggests or safely performs small useful actions
↓
Long-term patterns improve coaching and automation
```

---

## 2. Non-Negotiable Principles

### 2.1 Home Assistant is the source of truth

Rust core must not re-implement hardware detection logic.

Examples:

```text
Good:
- HA decides binary_sensor.supplement_magnesium_present is on/off.
- Rust core trusts that state and maps on->off to supplement.taken.magnesium.

Bad:
- Rust core directly polls NFC readers and decides bottle presence.
- Rust core duplicates HA template sensor logic.
```

### 2.2 Low friction beats perfect certainty

For interactions like supplement bottle removal:

```text
binary_sensor.supplement_magnesium_present: on -> off
```

Treat as consumed/taken if the physical interaction is intentionally designed that way.

Do not add probabilistic uncertainty models unless the user explicitly asks.

### 2.3 Calm, glanceable UI

The UI should not look like Prometheus, Grafana, or a router admin panel.

It should feel like:

```text
A personal morning/evening briefing
+ smart-home control room
+ health/routine coach
```

Tone:

```text
calm
specific
not alarmist
not chatty
not gamified unless useful
```

### 2.4 Explain why, not just what

Every recommendation should show its reason.

Example:

```text
Recommendation:
침실 10분 환기 추천

Why:
CO2 1,120ppm · 취침 시간대 · 최근 30분 활동 낮음
```

### 2.5 Human override first

The user can dismiss, snooze, approve, disable, or inspect every recommendation/action.

No hidden automations in the Rust layer.

---

## 3. Target System Shape

```text
Home Assistant
  ├─ sensors/helpers/events
  ├─ ActivityWatch-derived sensors
  ├─ Garmin-derived sensors
  ├─ supplement presence sensors
  └─ lights/climate/media/speakers
        ↓
Rust Personal Home OS Core
  ├─ ha client
  ├─ semantic mapper
  ├─ event ledger
  ├─ context builder
  ├─ routine planners
  ├─ briefing composer
  ├─ safety policy
  ├─ action executor
  └─ web UI/API
        ↓
User Interfaces
  ├─ local dashboard
  ├─ mobile-friendly dashboard
  ├─ spoken briefings
  ├─ notifications
  └─ optional chat/LLM interface
```

---

## 4. Current Rust Core State

Current directory:

```text
/home/yuyu/home-iot/personal-home-os
```

Current implemented modules:

```text
src/ha/types.rs
src/semantic/event.rs
src/semantic/mapper.rs
src/server.rs
```

Current implemented behavior:

```text
HA state_changed event model
supplement_magnesium_present on->off
→ supplement.taken.magnesium semantic event
```

Current UI/server:

```text
GET /            basic dashboard shell
GET /health      health JSON
GET /api/status  bootstrap status JSON
```

Current server port during development:

```text
18080
```

---

## 5. Final UX Vision

### 5.1 Home screen: “Now”

The default page should answer “what matters right now?” within 3 seconds.

URL:

```text
/
```

Sections:

```text
1. Current Briefing
2. Recommended Actions
3. Home State Highlights
4. Health / Energy State
5. Routine Progress
6. Recent Semantic Events
```

Example layout:

```text
┌─────────────────────────────────────────────────────────────┐
│ Personal Home OS                                  22:18 Thu │
│ 오늘은 회복이 낮고 침실 CO2가 높아요. 자기 전 환기와        │
│ 마그네슘을 챙기면 좋아요.                                  │
└─────────────────────────────────────────────────────────────┘

┌ Recommended Actions ────────────────────────────────────────┐
│ [중요] 침실 10분 환기                                      │
│ 이유: CO2 1,120ppm · 취침 전 · 최근 환기 없음              │
│ [실행] [10분 뒤] [오늘 숨김] [왜?]                         │
│                                                             │
│ [보통] 마그네슘 챙기기                                     │
│ 이유: 오늘 아직 taken 이벤트 없음                          │
│ [완료 처리] [나중에] [숨김]                                │
└─────────────────────────────────────────────────────────────┘

┌ Home ───────────────┐ ┌ Health ─────────────┐ ┌ Routines ───┐
│ 침실 CO2 1120 ppm   │ │ Body Battery 31     │ │ Night 2/4    │
│ 온도 22.8 ℃         │ │ Sleep Score 72      │ │ Supplements │
│ 조명 65%            │ │ Stress elevated     │ │ Mg missing  │
└─────────────────────┘ └─────────────────────┘ └─────────────┘
```

### 5.2 Visual style

Direction:

```text
Dark calm dashboard
Large readable cards
Soft contrast
No dense tables on first screen
Mobile-first responsive layout
```

Colors:

```text
background: near black / navy
cards: dark blue-gray
accent: cyan/blue
success: soft green
warning: warm amber
critical: muted red, only when truly urgent
```

Typography:

```text
Large title/status text
Short sentences
Korean-first user-facing copy
Numbers with units
Avoid raw entity IDs unless in debug/details mode
```

### 5.3 Interaction style

Primary interactions:

```text
Approve
Dismiss
Snooze
Explain
Mark done
Open details
```

Avoid:

```text
complex forms
raw YAML editing in the main UI
unclear toggle switches
multi-step setup on the home screen
```

---

## 6. Main Screens

### 6.1 Now Dashboard

Path:

```text
/
```

Purpose:

```text
Show current briefing and most relevant actions.
```

Data sources:

```text
data/context/now.json
latest routine planner output
action policy decisions
```

Cards:

```text
Current Briefing
Recommended Actions
Home Environment
Computer/Focus Context
Health/Energy
Supplements
Recent Events
```

Acceptance criteria:

```text
- Loads in browser without JS requirement.
- Shows useful content even when HA is disconnected.
- Clearly states when data is mock/stale/unavailable.
- Does not expose raw tokens/secrets.
```

### 6.2 Routines

Path:

```text
/routines
```

Purpose:

```text
Show routine progress and logic.
```

Initial routines:

```text
Night routine
Morning routine
Supplement routine
Work/focus routine
```

Night routine example:

```text
- Magnesium: missing
- Bedroom CO2: high
- Lights: not dimmed
- Computer mode: browsing/video
- Briefing: not done
```

The UI should show:

```text
current checklist
why each item matters
whether it is detected automatically or manually marked
```

### 6.3 Events

Path:

```text
/events
```

Purpose:

```text
Human-readable semantic event history.
```

Example rows:

```text
22:11  supplement.taken.magnesium    trusted    from binary_sensor.supplement_magnesium_present
21:48  environment.high_co2.bedroom  trusted    from sensor.bedroom_co2
18:02  computer.focus.started        trusted    from sensor.activitywatch_current_mode
```

UX rules:

```text
- Show semantic names first.
- Raw HA entity available in details.
- Filter by domain: supplement, environment, computer, health, routine.
- JSONL file remains the storage format.
```

### 6.4 Home State

Path:

```text
/home
```

Purpose:

```text
Show HA-derived state in user language.
```

Sections:

```text
Environment
Presence
Lights
Climate
Computer context
Health context
Supplements
```

Important:

```text
This is not a replacement for Home Assistant UI.
It only shows states relevant to personal routines and agent decisions.
```

### 6.5 Insights

Path:

```text
/insights
```

Purpose:

```text
Longer-term patterns from semantic events and context snapshots.
```

Examples:

```text
- Magnesium adherence this week: 5/7 days
- Bedroom CO2 above 1000ppm before sleep: 4 nights this week
- High screen time after 22:00 correlated with lower sleep score
- Body Battery below 35 on 3 consecutive evenings
```

This screen comes later. Do not build before ledger/context are stable.

### 6.6 Settings / Contracts

Path:

```text
/settings
```

Purpose:

```text
Show configuration health, not edit everything.
```

Initial content:

```text
HA connection status
Configured entity contract coverage
Missing entities
Runtime paths
Safety policy mode
```

Avoid building a full config editor early.

---

## 7. API Target

### 7.1 Health

```text
GET /health
```

Returns:

```json
{"status":"ok","service":"personal-home-os"}
```

### 7.2 Status

```text
GET /api/status
```

Returns:

```json
{
  "service": "personal-home-os",
  "status": "running",
  "runtime": "rust",
  "home_assistant": "connected|not_connected|error",
  "version": "0.1.0"
}
```

### 7.3 Current Context

```text
GET /api/now
```

Returns `now.json`:

```json
{
  "date": "2026-05-14",
  "time": "2026-05-14T22:10:00+09:00",
  "health": {},
  "environment": {},
  "computer": {},
  "supplements": {},
  "events_today": [],
  "recommended_actions": []
}
```

### 7.4 Events

```text
GET /api/events?date=2026-05-14&domain=supplement
```

Returns semantic events from JSONL ledger.

### 7.5 Actions

```text
POST /api/actions/:id/approve
POST /api/actions/:id/dismiss
POST /api/actions/:id/snooze
POST /api/actions/:id/execute
```

Rules:

```text
- execute must pass safety policy.
- unsafe actions return explanation, not silent failure.
- all user decisions are logged as semantic events.
```

---

## 8. Data Model Target

### 8.1 Semantic Event

```json
{
  "ts": "2026-05-14T22:11:04+09:00",
  "domain": "supplement",
  "type": "taken",
  "entity": "magnesium",
  "source_entity": "binary_sensor.supplement_magnesium_present",
  "old_state": "on",
  "new_state": "off",
  "trusted": true
}
```

Storage:

```text
personal-home-os/data/events/YYYY-MM-DD.jsonl
```

### 8.2 Now Context

```json
{
  "date": "2026-05-14",
  "time": "2026-05-14T22:18:00+09:00",
  "health": {
    "body_battery": 31,
    "sleep_score": 72
  },
  "environment": {
    "bedroom_co2": 1120,
    "bedroom_temperature": 22.8
  },
  "computer": {
    "current_mode": "video",
    "screen_after_22_minutes": 38,
    "in_meeting": false
  },
  "supplements": {
    "magnesium": "missing",
    "omega3": "taken"
  },
  "events_today": [],
  "recommended_actions": []
}
```

Storage:

```text
personal-home-os/data/context/now.json
```

### 8.3 Recommended Action

```json
{
  "id": "ventilate_bedroom",
  "title": "침실 10분 환기",
  "priority": "medium",
  "message": "침실 CO2가 높아서 10분 환기를 추천해요.",
  "reason": [
    "bedroom_co2=1120ppm",
    "night routine window",
    "not in meeting"
  ],
  "safety": {
    "auto_executable": false,
    "requires_approval": true
  },
  "ha_service": null
}
```

---

## 9. Routine Targets

### 9.1 Night Routine

Goal:

```text
Help the user transition to sleep with minimal nagging.
```

Inputs:

```text
current time
bedroom CO2/temp/humidity
lights
computer mode
meeting/focus status
supplement status
Garmin body battery/stress/sleep debt
briefing already done flag
```

Outputs:

```text
recommended actions
briefing text
optional HA actions
```

Example actions:

```text
take_magnesium
ventilate_bedroom
dim_lights_for_bedtime
stop_late_screen_drift
prepare_sleep_environment
```

Anti-annoyance rules:

```text
- Do not interrupt meetings.
- Do not interrupt deep focus unless health/safety critical.
- Do not repeat dismissed action too soon.
- Do not speak every recommendation; batch into briefing.
```

### 9.2 Morning Routine

Goal:

```text
Give a short situational briefing and suggest recovery/workload strategy.
```

Inputs:

```text
sleep score
body battery
weather if available
calendar later
home environment
computer activity from previous night
```

Outputs:

```text
morning briefing
recovery suggestion
work intensity suggestion
```

### 9.3 Supplement Routine

Goal:

```text
Track adherence automatically through HA helper/sensor events.
```

Inputs:

```text
supplement presence sensors
input_boolean.*_taken_today helpers
last_taken helpers
```

UX:

```text
Show simple taken/missing state.
Allow manual mark done.
Avoid guilt language.
```

---

## 10. Voice / Briefing UX

Voice is a later layer. The text composer comes first.

### 10.1 Briefing tone

Korean-first, short, natural:

```text
침실 CO2가 조금 높고, 마그네슘은 아직 안 챙기셨어요.
자기 전 10분만 환기하고 조명은 낮춰둘게요.
```

Avoid:

```text
- medical certainty
- excessive detail
- repeated nagging
- fake empathy
```

### 10.2 Briefing display

The dashboard should show:

```text
briefing text
source facts
actions included
spoken/not spoken status
last briefing time
```

### 10.3 Voice execution

Future:

```text
briefing text
→ TTS provider
→ HA media_player service
```

Must have:

```text
quiet hours policy
speaker target config
manual test button
rate limiting
```

---

## 11. Safety Model

Action types:

```text
Observe       read-only
Suggest       display only
Prepare       create action candidate
Execute Safe  low-risk HA service after policy
Execute Risky require explicit approval
Never         forbidden from Rust agent
```

Initially auto-executable candidates:

```text
light brightness changes within configured room/time
turning on fan/ventilation if configured safe
setting helper booleans/datetimes
```

Requires approval:

```text
locks
doors
appliances
thermostat large changes
anything outside allowlist
```

Never early:

```text
security system changes
external purchases
medical advice automation
unbounded LLM tool execution
```

---

## 12. UX States to Handle

Every screen must have good states for:

```text
Loading
No HA connection
HA connected but entity missing
Data stale
No recommendations
Action dismissed
Action failed
Action executed
Server degraded
```

Example copy:

```text
HA 연결 대기 중입니다. 지금은 Rust core 상태만 표시합니다.
```

```text
침실 CO2 entity가 아직 설정되지 않았습니다. Settings에서 entity_contract를 확인하세요.
```

---

## 13. Implementation Roadmap

### Phase 0: UI shell, current state

Already partly done.

Tasks:

```text
- Keep dashboard shell at /
- Keep /health and /api/status
- Add no-crash behavior for malformed requests
- Use port 18080 during WSL development
```

### Phase 1: Ledger

Goal:

```text
SemanticEvent → JSONL daily files
```

Files:

```text
src/semantic/ledger.rs
src/semantic/mod.rs
tests/semantic_ledger_test.rs
```

UI impact:

```text
/events can show real recent semantic events
```

### Phase 2: Context Builder

Goal:

```text
HA state snapshot + today events → now.json
```

Files:

```text
src/context/mod.rs
src/context/builder.rs
src/context/types.rs
tests/context_builder_test.rs
```

UI impact:

```text
/ and /api/now show actual context sections
```

### Phase 3: Night Routine Planner

Goal:

```text
now context → recommended_actions
```

Files:

```text
src/routines/mod.rs
src/routines/night.rs
tests/night_routine_test.rs
```

UI impact:

```text
Recommended Actions card becomes real
```

### Phase 4: Briefing Composer

Goal:

```text
recommended_actions + context → Korean briefing text
```

Files:

```text
src/briefing/mod.rs
src/briefing/night.rs
tests/briefing_test.rs
```

UI impact:

```text
Current Briefing card becomes real
```

### Phase 5: HA Client

Goal:

```text
Read HA states and receive HA events
```

Files:

```text
src/ha/client.rs
src/ha/ws.rs
src/ha/state.rs
```

UI impact:

```text
Settings shows HA connection status
Home State cards show actual HA-derived values
```

### Phase 6: Safe Action Executor

Goal:

```text
recommended action → safety policy → HA service call
```

Files:

```text
src/action/mod.rs
src/action/policy.rs
src/action/executor.rs
```

UI impact:

```text
Action buttons can execute real low-risk actions
```

### Phase 7: Better UI runtime

Only after data is real.

Options:

```text
Keep server-rendered HTML
Add HTMX for partial refresh
Add Server-Sent Events for live updates
Only consider frontend framework if UI complexity demands it
```

---

## 14. What Not To Build Yet

Do not build these before ledger/context/routines are working:

```text
full config editor
complex auth
mobile app
React/Vue/Svelte app
LLM autonomous action execution
multi-user support
cloud sync
predictive ML models
```

Reason:

```text
They add surface area before the core behavior is proven.
```

---

## 15. First Real MVP Acceptance Criteria

The MVP is complete when this is true:

```text
1. Rust server runs locally on a non-conflicting port.
2. HA connection status is visible.
3. A HA state_changed event can become a SemanticEvent.
4. SemanticEvent is appended to daily JSONL ledger.
5. now.json is built from HA states + today's events.
6. Dashboard / shows current briefing and recommended actions from now.json.
7. /events shows recent semantic events in human-readable form.
8. Night routine can recommend at least:
   - take_magnesium
   - ventilate_bedroom
   - dim_lights_for_bedtime
9. User can dismiss/snooze/approve actions in the UI.
10. Safe HA service action can execute only through allowlist policy.
11. All tests pass:
    cargo fmt --check
    cargo test
    cargo clippy --all-targets --all-features -- -D warnings
```

---

## 16. File Ownership

Rust reboot canonical files:

```text
personal-home-os/src/**
personal-home-os/config/**
personal-home-os/data/**
personal-home-os/tests/**
```

Planning/docs:

```text
docs/plans/rust-personal-home-os-reboot-plan.md
docs/plans/personal-home-os-product-ui-ux-target.md
```

Old Python reference only:

```text
agent/**
```

Do not delete old Python code until Rust has feature parity for the core loop.

---

## 17. Product Copy Guidelines

Use Korean for user-facing routine/briefing text.

Good:

```text
마그네슘은 아직 안 챙기셨어요.
침실 CO2가 높아서 10분 환기를 추천해요.
회의 중이라 루틴 알림은 미뤘어요.
```

Bad:

```text
ALERT: MAGNESIUM NON-COMPLIANCE
You failed to take supplement.
CO2 threshold exceeded.
```

Tone:

```text
calm
specific
actionable
non-judgmental
```

---

## 18. Development Rules

Use TDD for domain behavior:

```text
semantic mapper
ledger
context builder
routine planner
briefing composer
action policy
```

Before each commit:

```bash
cd /home/yuyu/home-iot/personal-home-os
cargo fmt --check
cargo test
cargo clippy --all-targets --all-features -- -D warnings
```

Commit style:

```text
feat: add semantic event ledger
feat: build current context
feat: plan night routine actions
feat: compose night briefing
fix: keep server alive on malformed requests
docs: update product target
```

---

## 19. Immediate Next Step

Next implementation should be:

```text
Phase 1: JSONL semantic event ledger
```

Why:

```text
The UI needs real history, and context builder needs today_events.
```

Do not jump directly to fancy UI. The dashboard should become useful by wiring real data into simple cards.

Recommended next files:

```text
Create: personal-home-os/src/semantic/ledger.rs
Modify: personal-home-os/src/semantic/mod.rs
Create: personal-home-os/tests/semantic_ledger_test.rs
```

Expected behavior:

```text
SemanticEvent
→ append one JSON line to data/events/YYYY-MM-DD.jsonl
→ read events for a date
→ ignore malformed lines without crashing, but report count later
```

---

## 20. Final Product Summary

Personal Home OS should become:

```text
A local, HA-centered, Rust-powered personal home/health agent
with a calm Korean-first dashboard,
trusted semantic event history,
current context awareness,
routine recommendations,
safe Home Assistant actions,
and eventually voice briefings.
```

It should not become:

```text
a generic HA clone
a metrics dashboard
a chatbot-first toy
a fragile collection of scripts
a system that demands constant manual logging
```

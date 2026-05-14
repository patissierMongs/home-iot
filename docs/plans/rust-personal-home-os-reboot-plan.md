# Rust Personal Home OS Reboot Plan

> **Status:** Planning only. Do not implement Rust code until this plan is reviewed.

**Goal:** Rebuild the Personal Home OS agent as a clean, modular Rust core in a new directory, without extending the existing Python `agent/` implementation.

**Reason for reboot:** The current Python branch proved the architecture direction, but mixing the new Personal Home OS design into the existing Python agent can become confusing. The next iteration should start fresh, keep modules explicit, and use the existing Python work only as reference.

**Core rule:** Home Assistant remains the source of truth for device state, sensor fusion, helpers, and hardware detection. The Rust agent consumes HA states/events and produces semantic events, context, recommendations, briefings, and safe HA service calls.

---

## 1. New Directory

Create a new top-level directory under the repo:

```text
/home/yuyu/home-iot/personal-home-os/
```

This directory is independent from:

```text
/home/yuyu/home-iot/agent/
```

The old Python `agent/` stays as reference and should not be modified during the Rust reboot unless explicitly needed for migration notes.

Proposed structure:

```text
personal-home-os/
├── Cargo.toml
├── README.md
├── config/
│   ├── entity_contract.yaml
│   ├── semantic_entities.yaml
│   └── runtime.yaml.example
├── data/
│   ├── events/.gitkeep
│   └── context/.gitkeep
├── src/
│   ├── main.rs
│   ├── lib.rs
│   ├── config.rs
│   ├── ha/
│   │   ├── mod.rs
│   │   ├── client.rs
│   │   └── types.rs
│   ├── semantic/
│   │   ├── mod.rs
│   │   ├── event.rs
│   │   ├── mapper.rs
│   │   └── ledger.rs
│   ├── context/
│   │   ├── mod.rs
│   │   └── builder.rs
│   ├── routines/
│   │   ├── mod.rs
│   │   └── night.rs
│   ├── briefing/
│   │   ├── mod.rs
│   │   └── composer.rs
│   ├── action/
│   │   ├── mod.rs
│   │   ├── policy.rs
│   │   └── executor.rs
│   └── runtime/
│       ├── mod.rs
│       └── agent.rs
└── tests/
    ├── semantic_mapper_test.rs
    ├── event_ledger_test.rs
    ├── context_builder_test.rs
    ├── night_routine_test.rs
    ├── briefing_test.rs
    └── action_policy_test.rs
```

## 2. What to Carry Over Conceptually

Carry over the architecture, not the Python code.

From the current Python branch:

```text
agent/config/entity_contract.yaml
agent/config/semantic_entities.yaml
agent/src/home_iot/events.py
agent/src/home_iot/semantic.py
agent/src/home_iot/semantic_runtime.py
agent/src/home_iot/context.py
agent/src/home_iot/routines/night.py
```

Use them only as behavior references.

Rust modules should be designed around these concepts:

```text
HA state_changed event
  → SemanticEventMapper
  → SemanticEvent
  → EventLedger JSONL
  → ContextBuilder
  → recommended_actions
  → BriefingComposer
  → ActionPolicy / ActionExecutor
```

## 3. Rust Crate Setup

Use one binary crate with a library module:

```bash
cd /home/yuyu/home-iot
cargo new personal-home-os --bin
```

Expected crate layout after setup:

```text
personal-home-os/Cargo.toml
personal-home-os/src/main.rs
```

Then add `src/lib.rs` and modules manually.

Initial dependencies:

```toml
[dependencies]
anyhow = "1"
chrono = { version = "0.4", features = ["serde"] }
clap = { version = "4", features = ["derive"] }
reqwest = { version = "0.12", features = ["json", "rustls-tls"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
serde_yaml = "0.9"
tokio = { version = "1", features = ["macros", "rt-multi-thread", "time"] }
tracing = "0.1"
tracing-subscriber = "0.3"

[dev-dependencies]
tempfile = "3"
```

Keep dependencies minimal. Do not add database, TTS, Garmin, or ActivityWatch crates in the first slice.

## 4. Configuration Model

### 4.1 Entity Contract

File:

```text
personal-home-os/config/entity_contract.yaml
```

Purpose:

- Defines HA entities the Rust agent can depend on.
- Avoids hard-coded entity IDs in logic.

Initial shape:

```yaml
health:
  body_battery: sensor.garmin_body_battery
  sleep_score: sensor.garmin_sleep_score

environment:
  bedroom_co2: sensor.bedroom_co2
  bedroom_temperature: sensor.bedroom_temperature

computer:
  current_mode: sensor.computer_current_mode
  focus_block_minutes: sensor.computer_focus_block_minutes
  screen_after_22_minutes: sensor.computer_screen_after_22_minutes
  in_meeting: binary_sensor.computer_in_meeting

routines:
  night_briefing_done: input_boolean.night_briefing_done
  target_bedtime: input_datetime.target_bedtime

supplements:
  magnesium:
    taken_today: input_boolean.supplement_magnesium_taken_today
    last_taken: input_datetime.supplement_magnesium_last_taken
```

### 4.2 Semantic Entities

File:

```text
personal-home-os/config/semantic_entities.yaml
```

Initial shape:

```yaml
supplements:
  magnesium:
    present_entity: binary_sensor.supplement_magnesium_present
    taken_transition: ["on", "off"]
    taken_helper: input_boolean.supplement_magnesium_taken_today
    last_taken_helper: input_datetime.supplement_magnesium_last_taken

presence:
  user_home:
    entity: binary_sensor.user_home
    arrived_transition: ["off", "on"]
    left_transition: ["on", "off"]

routines:
  shower:
    entity: binary_sensor.shower_done_today
    done_transition: ["off", "on"]
```

### 4.3 Runtime Config

File:

```text
personal-home-os/config/runtime.yaml.example
```

Purpose:

- Runtime paths.
- HA connection settings from env var names, not secrets.
- Safety options.

Example:

```yaml
home_assistant:
  base_url_env: HA_BASE_URL
  token_env: HA_TOKEN

paths:
  event_dir: data/events
  context_path: data/context/now.json

safety:
  auto_execute_actions: false
  allowlisted_action_ids:
    - dim_lights_for_bedtime
```

Do not commit real HA URLs/tokens.

## 5. Module Responsibilities

### 5.1 `config`

Files:

```text
src/config.rs
```

Responsibilities:

- Load YAML config files.
- Deserialize into typed structs.
- Validate required sections.

First tests:

- Loads entity contract YAML.
- Loads semantic entities YAML.
- Fails clearly on invalid YAML.

### 5.2 `ha`

Files:

```text
src/ha/mod.rs
src/ha/client.rs
src/ha/types.rs
```

Responsibilities:

- Define HA state/event/service-call types.
- Provide HA REST client later.
- In first slice, keep HTTP client minimal or mocked behind trait.

Important types:

```rust
pub struct HaStateChangedEvent {
    pub entity_id: String,
    pub old_state: Option<String>,
    pub new_state: String,
    pub time_fired: DateTime<Utc>,
}

pub struct HaServiceCall {
    pub domain: String,
    pub service: String,
    pub target: serde_json::Value,
    pub data: serde_json::Value,
}
```

### 5.3 `semantic`

Files:

```text
src/semantic/event.rs
src/semantic/mapper.rs
src/semantic/ledger.rs
```

Responsibilities:

- Convert HA state changes to semantic events.
- Persist semantic events as JSONL.

Important behavior:

```text
binary_sensor.supplement_magnesium_present on→off
  → supplement.taken.magnesium trusted=true
```

Event ledger output:

```text
data/events/YYYY-MM-DD.jsonl
```

### 5.4 `context`

Files:

```text
src/context/builder.rs
```

Responsibilities:

- Read HA states via trait.
- Read today's JSONL event ledger.
- Build `CurrentContext` struct.
- Write `data/context/now.json`.

Initial context sections:

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

### 5.5 `routines`

Files:

```text
src/routines/night.rs
```

Responsibilities:

- Pure deterministic planners.
- No HA calls.
- No TTS.
- No LLM.

Initial night routine behavior:

```text
If 21:00-23:59
and night_briefing_done != on
and not in meeting
and not in long coding focus block:
  - magnesium missing → take_magnesium
  - bedroom_co2 >= 900 → ventilate_bedroom
  - if any medium action exists → dim_lights_for_bedtime candidate
```

### 5.6 `briefing`

Files:

```text
src/briefing/composer.rs
```

Responsibilities:

- Convert recommended actions into concise Korean text.
- No TTS yet.

Example:

```text
마그네슘 아직 안 챙기셨어요. 침실 CO2가 940ppm이라 10분 환기 추천드려요.
```

### 5.7 `action`

Files:

```text
src/action/policy.rs
src/action/executor.rs
```

Responsibilities:

- Decide which actions are allowed to execute automatically.
- Execute HA service calls only if allowed.
- Record action events later.

Initial safety rule:

```text
Only allowlisted action IDs may execute.
Never execute curtain/fingerbot/lock/security actions by default.
```

### 5.8 `runtime`

Files:

```text
src/runtime/agent.rs
```

Responsibilities:

- Wire modules together.
- Later: HA websocket loop or periodic tick.
- First slice can expose a function like:

```rust
process_state_changed(event) -> RuntimeResult
```

## 6. TDD Implementation Plan

Use strict TDD. No production Rust module without a failing test first.

### Task 1: Scaffold Rust Crate

Objective:

Create the new Rust crate without implementing behavior.

Commands:

```bash
cd /home/yuyu/home-iot
cargo new personal-home-os --bin
cd personal-home-os
cargo test
```

Expected:

```text
test result: ok
```

Commit:

```bash
git add personal-home-os
git commit -m "chore: scaffold Rust Personal Home OS crate"
```

### Task 2: Semantic Mapper Test and Implementation

Objective:

Map HA supplement presence transition into a semantic event.

Test file:

```text
personal-home-os/tests/semantic_mapper_test.rs
```

Expected behavior:

```text
entity_id = binary_sensor.supplement_magnesium_present
old_state = on
new_state = off
→ event domain=supplement type=taken entity=magnesium trusted=true
```

Run RED:

```bash
cd /home/yuyu/home-iot/personal-home-os
cargo test semantic_mapper -- --nocapture
```

Expected:

```text
FAIL: unresolved module or missing mapper
```

Then implement:

```text
src/ha/types.rs
src/semantic/event.rs
src/semantic/mapper.rs
src/semantic/mod.rs
src/lib.rs
```

Run GREEN:

```bash
cargo test semantic_mapper -- --nocapture
cargo test
```

Commit:

```bash
git add personal-home-os
git commit -m "feat: add Rust semantic event mapper"
```

### Task 3: Event Ledger Test and Implementation

Objective:

Append semantic events to date-based JSONL files.

Test file:

```text
personal-home-os/tests/event_ledger_test.rs
```

Expected behavior:

```text
SemanticEvent at 2026-05-13T22:11:04Z
→ data/events/2026-05-13.jsonl
→ one JSON line with domain/type/entity/trusted fields
```

Implementation file:

```text
src/semantic/ledger.rs
```

Commit:

```bash
git add personal-home-os
git commit -m "feat: add Rust semantic event ledger"
```

### Task 4: Night Routine Planner Test and Implementation

Objective:

Generate recommended actions from context without HA calls.

Test file:

```text
personal-home-os/tests/night_routine_test.rs
```

Expected behavior:

```text
magnesium missing + bedroom_co2 940 + video mode + night window
→ take_magnesium
→ ventilate_bedroom
→ dim_lights_for_bedtime
```

Implementation file:

```text
src/routines/night.rs
```

Commit:

```bash
git add personal-home-os
git commit -m "feat: add Rust night routine planner"
```

### Task 5: Context Builder Test and Implementation

Objective:

Build `now.json` from mocked HA state plus today's ledger.

Test file:

```text
personal-home-os/tests/context_builder_test.rs
```

Expected behavior:

```text
HA states + event ledger
→ CurrentContext
→ data/context/now.json
→ includes recommended_actions
```

Implementation files:

```text
src/context/mod.rs
src/context/builder.rs
```

Commit:

```bash
git add personal-home-os
git commit -m "feat: add Rust current context builder"
```

### Task 6: Briefing Composer Test and Implementation

Objective:

Convert recommended actions into concise Korean text.

Test file:

```text
personal-home-os/tests/briefing_test.rs
```

Expected behavior:

```text
[take_magnesium, ventilate_bedroom]
→ "마그네슘 아직 안 챙기셨어요. 침실 CO2가 940ppm이라 10분 환기 추천드려요."
```

Implementation file:

```text
src/briefing/composer.rs
```

Commit:

```bash
git add personal-home-os
git commit -m "feat: add Rust briefing composer"
```

### Task 7: Action Policy Test and Implementation

Objective:

Ensure only safe allowlisted actions execute.

Test file:

```text
personal-home-os/tests/action_policy_test.rs
```

Expected behavior:

```text
allowlisted dim_lights_for_bedtime → allowed
curtain/fingerbot action → denied by default
unknown action → denied
```

Implementation file:

```text
src/action/policy.rs
```

Commit:

```bash
git add personal-home-os
git commit -m "feat: add Rust action safety policy"
```

### Task 8: Runtime Wiring Test and Implementation

Objective:

Process one HA state change through the pipeline.

Test file:

```text
personal-home-os/tests/runtime_pipeline_test.rs
```

Expected behavior:

```text
HA state_changed supplement event
→ semantic event recorded
→ helper service call proposed or emitted
→ context rebuilt
→ recommended_actions available
```

Implementation files:

```text
src/runtime/mod.rs
src/runtime/agent.rs
```

Commit:

```bash
git add personal-home-os
git commit -m "feat: wire Rust Personal Home OS pipeline"
```

## 7. First Rust MVP Definition of Done

The first Rust MVP is done when this command passes:

```bash
cd /home/yuyu/home-iot/personal-home-os
cargo fmt --check
cargo test
cargo clippy --all-targets --all-features -- -D warnings
```

And the crate can perform this tested flow:

```text
HA state_changed event
  → semantic event
  → JSONL ledger
  → now.json
  → recommended_actions
  → Korean briefing text
  → safety policy decision for optional HA action
```

No real HA connection is required for the first MVP. Use traits and fake clients in tests.

## 8. Migration Policy

Do not delete the Python `agent/` yet.

Use it as:

```text
reference implementation
behavior sample
fallback while Rust core matures
```

Only after the Rust crate reaches end-to-end parity should we decide whether to:

```text
- keep Python agent for legacy importers/tools
- move Python-only bridges behind CLI commands
- retire Python runtime loop
```

## 9. Immediate Next Step After Plan Approval

1. Ensure Rust toolchain is installed.
2. Run:

```bash
cd /home/yuyu/home-iot
cargo new personal-home-os --bin
```

3. Add minimal dependencies.
4. Start Task 2 with a failing semantic mapper test.

Do not start by building the HA client. Start with pure domain behavior first.

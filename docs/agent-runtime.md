# HA-Centered Agent Runtime

This branch turns the home-iot agent into a semantic layer above Home Assistant.

## Principle

Home Assistant is the source of truth for physical state and low-level detection.
The agent does not infer whether a sensor is correct, how a supplement slot is
wired, or how a routine detector works. It consumes HA entities/events, records
trusted semantic events, builds context, and acts through HA service calls.

## Current Flow

```text
HA state_changed event
  ↓
SemanticEventRuntime
  ↓
SemanticEventMapper
  ↓
EventLedger JSONL
  ↓
HA helper update, when configured
  ↓
ContextBuilder
  ↓
agent/data/context/now.json
  ↓
RuleEngine / LLM path
```

## Config Files

### `agent/config/entity_contract.yaml`

Defines the HA entities the agent is allowed to depend on.

Examples:

```yaml
health:
  body_battery: sensor.garmin_body_battery

environment:
  bedroom_co2: sensor.bedroom_co2

supplements:
  magnesium:
    taken_today: input_boolean.supplement_magnesium_taken_today
```

Do not hard-code entity IDs in agent logic. Add or rename entities here.

### `agent/config/semantic_entities.yaml`

Defines trusted HA state transitions that become semantic events.

Example:

```yaml
supplements:
  magnesium:
    present_entity: binary_sensor.supplement_magnesium_present
    taken_transition: ["on", "off"]
    taken_helper: input_boolean.supplement_magnesium_taken_today
    last_taken_helper: input_datetime.supplement_magnesium_last_taken
```

This means:

```text
binary_sensor.supplement_magnesium_present: on → off
= supplement.taken.magnesium
```

The agent treats this as trusted. It does not ask whether the supplement was
actually swallowed.

## Runtime Outputs

### Semantic events

```text
agent/data/events/YYYY-MM-DD.jsonl
```

Example line:

```json
{"domain":"supplement","type":"taken","entity":"magnesium","trusted":true}
```

### Current context

```text
agent/data/context/now.json
```

The context builder reads `entity_contract.yaml`, queries HA state, reads today's
semantic event ledger, and writes a compact JSON object for routines/LLM use.

Current sections:

```text
health
environment
computer
presence
routines
supplements
events_today
```

## Current MVP Behavior

For supplements:

```text
HA detects bottle removed
  → binary_sensor.supplement_magnesium_present changes on→off
  → agent records supplement.taken.magnesium
  → agent turns on input_boolean.supplement_magnesium_taken_today
  → agent sets input_datetime.supplement_magnesium_last_taken
  → agent rebuilds now.json
```

## Verification

Run:

```bash
cd /home/yuyu/home-iot/agent
uv run pytest -q
uv run python -m compileall -q src
```

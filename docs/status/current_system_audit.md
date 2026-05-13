# Current System Audit

Date: 2026-05-13
Branch: `feat/personal-home-os-ha-agent`
Baseline tag: `stable-before-personal-home-os`

## Git

The repository is already under git version control and tracks GitHub remote:

- Remote: `https://github.com/patissierMongs/home-iot.git`
- Current branch: `feat/personal-home-os-ha-agent`
- Baseline commit/tag before redesign: `66b0d6d`, `stable-before-personal-home-os`

Recent history:

```text
66b0d6d (HEAD -> feat/personal-home-os-ha-agent, tag: stable-before-personal-home-os, origin/main, origin/feat/personal-home-os-ha-agent, main) chore: ignore local virtualenv
d5d7a27 Grafana Integrated Analytics dashboard + auto-refresh
fb6ec62 Add integrated Life Analytics engine — cross-dimensional statistical analysis
abbcf9e Add Qingping Air Monitor cloud API -> MQTT bridge
abbcf9e Add Qingping Air Monitor cloud API -> MQTT bridge
edede67 ORBITAL Life Explorer — premium mission-control dashboard
```

## Docker Stack

Observed with `docker compose -f stack/docker-compose.yml ps`:

```text
NAME      IMAGE                    COMMAND     SERVICE   CREATED       STATUS       PORTS
grafana   grafana/grafana:latest   "/run.sh"   grafana   5 weeks ago   Up 5 hours
```

Only Grafana is currently running. Home Assistant, Mosquitto, InfluxDB, Ollama, and Telegraf are defined in the stack but were not running at audit time.

## Agent Codebase

Existing source files:

```text
agent/src/home_iot/agent.py
agent/src/home_iot/analytics.py
agent/src/home_iot/bridges/activitywatch.py
agent/src/home_iot/bridges/qingping.py
agent/src/home_iot/config.py
agent/src/home_iot/ha.py
agent/src/home_iot/importers/samsung_health.py
agent/src/home_iot/importers/sleep_as_android.py
agent/src/home_iot/llm.py
agent/src/home_iot/main.py
agent/src/home_iot/rules.py
agent/src/home_iot/tools.py
```

## Compile Check

Command:

```bash
cd agent && uv run python -m compileall -q src
```

Result: PASS.

## Redesign Direction

The redesign will preserve Home Assistant as the source of truth:

- HA owns physical integrations, device state, template sensors, helpers, and low-level detection logic.
- The agent consumes HA states/events and does not re-implement hardware/sensor inference.
- The agent maps HA state changes to trusted semantic events, builds daily/current context, performs analytics, and acts via HA service calls.

Initial implementation target:

1. Define an entity contract and semantic entity mapping.
2. Add a semantic event mapper for HA `state_changed` events.
3. Add an event ledger storing trusted semantic events as JSONL.
4. Start with supplement presence entities as the first end-to-end flow.

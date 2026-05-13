from __future__ import annotations

import asyncio
from typing import Any

from home_iot.agent import Agent


class FakeRules:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def dispatch(self, event: dict[str, Any]) -> bool:
        self.events.append(event)
        return False


class FakeSemanticRuntime:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def handle_ha_event(self, event: dict[str, Any]) -> object | None:
        self.events.append(event)
        return object()


class FakeContextBuilder:
    def __init__(self) -> None:
        self.calls = 0

    async def build_now(self) -> dict[str, Any]:
        self.calls += 1
        return {"ok": True}


def test_agent_records_semantic_events_before_rule_and_llm_processing() -> None:
    agent = Agent.__new__(Agent)
    agent.rules = FakeRules()
    agent.semantic_runtime = FakeSemanticRuntime()
    agent.context_builder = FakeContextBuilder()
    agent._enable_llm = False
    agent.llm = None

    ha_event = {
        "event_type": "state_changed",
        "data": {
            "entity_id": "binary_sensor.supplement_magnesium_present",
            "old_state": {"state": "on"},
            "new_state": {"state": "off"},
        },
    }

    asyncio.run(agent.handle_event(ha_event))

    assert agent.semantic_runtime.events == [ha_event]
    assert agent.context_builder.calls == 1
    assert agent.rules.events == [ha_event]


def test_agent_continues_when_semantic_runtime_is_absent_for_compatibility() -> None:
    agent = Agent.__new__(Agent)
    agent.rules = FakeRules()
    agent._enable_llm = False
    agent.llm = None

    ha_event = {
        "event_type": "state_changed",
        "data": {
            "entity_id": "binary_sensor.anything",
            "old_state": {"state": "off"},
            "new_state": {"state": "on"},
        },
    }

    asyncio.run(agent.handle_event(ha_event))

    assert agent.rules.events == [ha_event]

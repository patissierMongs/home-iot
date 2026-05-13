from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from home_iot.context import ContextBuilder
from home_iot.events import EventLedger, SemanticEvent


class FakeHA:
    def __init__(self, states: dict[str, Any]) -> None:
        self.states = states

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        if entity_id not in self.states:
            raise KeyError(entity_id)
        value = self.states[entity_id]
        if isinstance(value, dict):
            return {"entity_id": entity_id, **value}
        return {"entity_id": entity_id, "state": value, "attributes": {}}


def test_context_builder_reads_contract_states_and_today_events(tmp_path: Path) -> None:
    ledger = EventLedger(tmp_path / "events")
    ledger.record(
        SemanticEvent(
            ts=datetime(2026, 5, 13, 22, 11, 4, tzinfo=timezone.utc),
            domain="supplement",
            type="taken",
            entity="magnesium",
            source_entity="binary_sensor.supplement_magnesium_present",
        )
    )
    ledger.record(
        SemanticEvent(
            ts=datetime(2026, 5, 13, 18, 45, 0, tzinfo=timezone.utc),
            domain="presence",
            type="arrived_home",
            entity="user",
        )
    )

    contract = {
        "health": {
            "body_battery": "sensor.garmin_body_battery",
            "sleep_score": "sensor.garmin_sleep_score",
        },
        "environment": {
            "bedroom_co2": "sensor.bedroom_co2",
            "bedroom_temperature": "sensor.bedroom_temperature",
        },
        "supplements": {
            "magnesium": {
                "taken_today": "input_boolean.supplement_magnesium_taken_today",
            },
            "omega3": {
                "taken_today": "input_boolean.supplement_omega3_taken_today",
            },
        },
        "computer": {
            "current_mode": "sensor.computer_current_mode",
            "screen_after_22_minutes": "sensor.computer_screen_after_22_minutes",
        },
    }
    ha = FakeHA(
        {
            "sensor.garmin_body_battery": "31",
            "sensor.garmin_sleep_score": "72",
            "sensor.bedroom_co2": {"state": "910", "attributes": {"unit_of_measurement": "ppm"}},
            "sensor.bedroom_temperature": "22.8",
            "input_boolean.supplement_magnesium_taken_today": "off",
            "input_boolean.supplement_omega3_taken_today": "on",
            "sensor.computer_current_mode": "video",
            "sensor.computer_screen_after_22_minutes": "38",
        }
    )

    builder = ContextBuilder(
        ha=ha,
        entity_contract=contract,
        event_dir=tmp_path / "events",
        output_path=tmp_path / "context" / "now.json",
    )

    context = asyncio.run(builder.build_now(now=datetime(2026, 5, 13, 22, 34, tzinfo=timezone.utc)))

    assert context["date"] == "2026-05-13"
    assert context["health"]["body_battery"] == 31
    assert context["health"]["sleep_score"] == 72
    assert context["environment"]["bedroom_co2"] == 910
    assert context["environment"]["bedroom_temperature"] == 22.8
    assert context["supplements"] == {"magnesium": "missing", "omega3": "taken"}
    assert context["computer"]["current_mode"] == "video"
    assert context["computer"]["screen_after_22_minutes"] == 38
    assert context["events_today"][0]["domain"] == "supplement"
    assert context["events_today"][0]["entity"] == "magnesium"
    assert [action["id"] for action in context["recommended_actions"]] == [
        "take_magnesium",
        "ventilate_bedroom",
        "dim_lights_for_bedtime",
    ]

    saved = json.loads((tmp_path / "context" / "now.json").read_text(encoding="utf-8"))
    assert saved == context


def test_context_builder_marks_missing_entities_as_unavailable(tmp_path: Path) -> None:
    builder = ContextBuilder(
        ha=FakeHA({}),
        entity_contract={"health": {"body_battery": "sensor.garmin_body_battery"}},
        event_dir=tmp_path / "events",
        output_path=tmp_path / "now.json",
    )

    context = asyncio.run(builder.build_now(now=datetime(2026, 5, 13, tzinfo=timezone.utc)))

    assert context["health"]["body_battery"] == "unavailable"

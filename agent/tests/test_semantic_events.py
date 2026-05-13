from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from home_iot.events import EventLedger, SemanticEvent
from home_iot.semantic import SemanticEventMapper


def test_maps_supplement_present_on_to_off_to_trusted_taken_event() -> None:
    mapper = SemanticEventMapper.from_config(
        {
            "supplements": {
                "magnesium": {
                    "display_name": "마그네슘",
                    "present_entity": "binary_sensor.supplement_magnesium_present",
                    "taken_transition": ["on", "off"],
                    "taken_helper": "input_boolean.supplement_magnesium_taken_today",
                    "last_taken_helper": "input_datetime.supplement_magnesium_last_taken",
                    "once_per_day": True,
                    "trusted": True,
                }
            }
        }
    )

    event = mapper.map_state_changed(
        entity_id="binary_sensor.supplement_magnesium_present",
        old_state="on",
        new_state="off",
        ts=datetime(2026, 5, 13, 22, 11, 4, tzinfo=timezone.utc),
    )

    assert event is not None
    assert event.domain == "supplement"
    assert event.type == "taken"
    assert event.entity == "magnesium"
    assert event.source == "home_assistant"
    assert event.source_entity == "binary_sensor.supplement_magnesium_present"
    assert event.old_state == "on"
    assert event.new_state == "off"
    assert event.trusted is True
    assert event.metadata["display_name"] == "마그네슘"
    assert event.metadata["taken_helper"] == "input_boolean.supplement_magnesium_taken_today"
    assert event.metadata["last_taken_helper"] == "input_datetime.supplement_magnesium_last_taken"


def test_ignores_non_matching_transition() -> None:
    mapper = SemanticEventMapper.from_config(
        {
            "supplements": {
                "magnesium": {
                    "present_entity": "binary_sensor.supplement_magnesium_present",
                    "taken_transition": ["on", "off"],
                }
            }
        }
    )

    event = mapper.map_state_changed(
        entity_id="binary_sensor.supplement_magnesium_present",
        old_state="off",
        new_state="on",
        ts=datetime(2026, 5, 13, tzinfo=timezone.utc),
    )

    assert event is None


def test_maps_presence_arrival_and_leaving() -> None:
    mapper = SemanticEventMapper.from_config(
        {
            "presence": {
                "user": {
                    "entity": "binary_sensor.user_home",
                    "arrived_transition": ["off", "on"],
                    "left_transition": ["on", "off"],
                    "trusted": True,
                }
            }
        }
    )

    arrived = mapper.map_state_changed(
        entity_id="binary_sensor.user_home",
        old_state="off",
        new_state="on",
        ts=datetime(2026, 5, 13, 18, 45, tzinfo=timezone.utc),
    )
    left = mapper.map_state_changed(
        entity_id="binary_sensor.user_home",
        old_state="on",
        new_state="off",
        ts=datetime(2026, 5, 13, 9, 0, tzinfo=timezone.utc),
    )

    assert arrived is not None
    assert arrived.domain == "presence"
    assert arrived.type == "arrived_home"
    assert arrived.entity == "user"
    assert left is not None
    assert left.domain == "presence"
    assert left.type == "left_home"
    assert left.entity == "user"


def test_event_ledger_writes_jsonl_by_event_date(tmp_path: Path) -> None:
    ledger = EventLedger(base_dir=tmp_path)
    event = SemanticEvent(
        ts=datetime(2026, 5, 13, 22, 11, 4, tzinfo=timezone.utc),
        domain="supplement",
        type="taken",
        entity="magnesium",
        source="home_assistant",
        source_entity="binary_sensor.supplement_magnesium_present",
        old_state="on",
        new_state="off",
        trusted=True,
        metadata={"display_name": "마그네슘"},
    )

    path = ledger.record(event)

    assert path == tmp_path / "2026-05-13.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["domain"] == "supplement"
    assert data["type"] == "taken"
    assert data["entity"] == "magnesium"
    assert data["trusted"] is True
    assert data["metadata"]["display_name"] == "마그네슘"

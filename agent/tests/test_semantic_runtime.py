from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from home_iot.semantic_runtime import SemanticEventRuntime


class FakeHA:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []

    async def call_service(
        self,
        domain: str,
        service: str,
        target: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((domain, service, target, data))
        return []


def make_state_event(entity_id: str, old: str, new: str, ts: str = "2026-05-13T22:11:04+00:00") -> dict[str, Any]:
    return {
        "event_type": "state_changed",
        "time_fired": ts,
        "data": {
            "entity_id": entity_id,
            "old_state": {"state": old, "attributes": {}},
            "new_state": {"state": new, "attributes": {}},
        },
    }


def test_runtime_records_semantic_event_and_updates_supplement_helpers(tmp_path: Path) -> None:
    ha = FakeHA()
    runtime = SemanticEventRuntime.from_config(
        config={
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
        },
        ledger_dir=tmp_path,
        ha=ha,
    )

    event = asyncio.run(
        runtime.handle_ha_event(
            make_state_event("binary_sensor.supplement_magnesium_present", "on", "off")
        )
    )

    assert event is not None
    assert event.domain == "supplement"
    assert event.type == "taken"
    assert (tmp_path / "2026-05-13.jsonl").exists()
    assert ha.calls == [
        (
            "input_boolean",
            "turn_on",
            {"entity_id": "input_boolean.supplement_magnesium_taken_today"},
            None,
        ),
        (
            "input_datetime",
            "set_datetime",
            {"entity_id": "input_datetime.supplement_magnesium_last_taken"},
            {"datetime": "2026-05-13 22:11:04"},
        ),
    ]


def test_runtime_ignores_non_state_changed_events(tmp_path: Path) -> None:
    ha = FakeHA()
    runtime = SemanticEventRuntime.from_config(config={}, ledger_dir=tmp_path, ha=ha)

    event = asyncio.run(runtime.handle_ha_event({"event_type": "call_service", "data": {}}))

    assert event is None
    assert ha.calls == []
    assert list(tmp_path.glob("*.jsonl")) == []


def test_runtime_uses_time_fired_when_available(tmp_path: Path) -> None:
    ha = FakeHA()
    runtime = SemanticEventRuntime.from_config(
        config={
            "presence": {
                "user": {
                    "entity": "binary_sensor.user_home",
                    "arrived_transition": ["off", "on"],
                    "left_transition": ["on", "off"],
                }
            }
        },
        ledger_dir=tmp_path,
        ha=ha,
    )

    event = asyncio.run(
        runtime.handle_ha_event(
            make_state_event("binary_sensor.user_home", "off", "on", "2026-05-13T18:45:21+09:00")
        )
    )

    assert event is not None
    assert event.ts.isoformat() == "2026-05-13T18:45:21+09:00"
    assert (tmp_path / "2026-05-13.jsonl").exists()
    assert ha.calls == []

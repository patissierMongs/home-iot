from __future__ import annotations

from datetime import datetime, timezone

from home_iot.routines.night import plan_night_routine


def test_night_routine_recommends_supplement_and_ventilation_and_light_dimming() -> None:
    context = {
        "health": {"body_battery": 29},
        "environment": {"bedroom_co2": 940},
        "computer": {"current_mode": "video", "screen_after_22_minutes": 38},
        "supplements": {"magnesium": "missing", "omega3": "taken"},
        "routines": {"target_bedtime": "23:10", "night_briefing_done": "off"},
    }

    actions = plan_night_routine(
        context,
        now=datetime(2026, 5, 13, 22, 30, tzinfo=timezone.utc),
    )

    assert [a["id"] for a in actions] == [
        "take_magnesium",
        "ventilate_bedroom",
        "dim_lights_for_bedtime",
    ]
    assert actions[0]["priority"] == "medium"
    assert "마그네슘" in actions[0]["message"]
    assert actions[1]["priority"] == "medium"
    assert "CO2" in actions[1]["message"]
    assert actions[2]["priority"] == "low"
    assert actions[2]["ha_service"] == {
        "domain": "light",
        "service": "turn_on",
        "target": {"entity_id": "light.bedroom"},
        "data": {"brightness_pct": 30},
    }


def test_night_routine_does_not_interrupt_focus_or_meeting_for_low_priority_items() -> None:
    context = {
        "environment": {"bedroom_co2": 720},
        "computer": {"current_mode": "coding", "focus_block_minutes": 75, "in_meeting": "off"},
        "supplements": {"magnesium": "taken"},
        "routines": {"night_briefing_done": "off"},
    }

    actions = plan_night_routine(
        context,
        now=datetime(2026, 5, 13, 22, 30, tzinfo=timezone.utc),
    )

    assert actions == []


def test_night_routine_skips_when_already_briefed() -> None:
    context = {
        "environment": {"bedroom_co2": 1200},
        "computer": {"current_mode": "video"},
        "supplements": {"magnesium": "missing"},
        "routines": {"night_briefing_done": "on"},
    }

    actions = plan_night_routine(
        context,
        now=datetime(2026, 5, 13, 22, 30, tzinfo=timezone.utc),
    )

    assert actions == []


def test_night_routine_only_runs_in_evening_window() -> None:
    context = {
        "environment": {"bedroom_co2": 1200},
        "computer": {"current_mode": "video"},
        "supplements": {"magnesium": "missing"},
        "routines": {"night_briefing_done": "off"},
    }

    actions = plan_night_routine(
        context,
        now=datetime(2026, 5, 13, 15, 0, tzinfo=timezone.utc),
    )

    assert actions == []

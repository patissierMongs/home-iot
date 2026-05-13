"""Deterministic night routine action planner.

This is intentionally not an LLM module. It converts the current context into a
small list of candidate actions. Later layers can decide whether to speak them,
call HA services, or ask an LLM to phrase them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def plan_night_routine(context: dict[str, Any], *, now: datetime) -> list[dict[str, Any]]:
    if not _is_evening_window(now):
        return []

    routines = _dict(context.get("routines"))
    if routines.get("night_briefing_done") == "on":
        return []

    computer = _dict(context.get("computer"))
    if _should_defer_for_focus(computer):
        return []

    actions: list[dict[str, Any]] = []
    supplements = _dict(context.get("supplements"))
    if supplements.get("magnesium") == "missing":
        actions.append(
            {
                "id": "take_magnesium",
                "priority": "medium",
                "message": "마그네슘 아직 안 챙기셨어요.",
            }
        )

    environment = _dict(context.get("environment"))
    bedroom_co2 = _number(environment.get("bedroom_co2"))
    if bedroom_co2 is not None and bedroom_co2 >= 900:
        actions.append(
            {
                "id": "ventilate_bedroom",
                "priority": "medium",
                "message": f"침실 CO2가 {int(bedroom_co2)}ppm이라 10분 환기 추천드려요.",
            }
        )

    if actions:
        actions.append(
            {
                "id": "dim_lights_for_bedtime",
                "priority": "low",
                "message": "취침 준비를 위해 침실 조명을 낮춰둘게요.",
                "ha_service": {
                    "domain": "light",
                    "service": "turn_on",
                    "target": {"entity_id": "light.bedroom"},
                    "data": {"brightness_pct": 30},
                },
            }
        )

    return actions


def _is_evening_window(now: datetime) -> bool:
    # Keep MVP simple: 21:00–23:59 local/runtime time.
    return 21 <= now.hour <= 23


def _should_defer_for_focus(computer: dict[str, Any]) -> bool:
    if computer.get("in_meeting") == "on":
        return True
    focus_minutes = _number(computer.get("focus_block_minutes"), 0) or 0
    if computer.get("current_mode") == "coding" and focus_minutes >= 45:
        return True
    return False


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default

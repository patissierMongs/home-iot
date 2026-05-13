"""Build LLM/routine-friendly current context from HA state and event ledger."""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml

from .routines.night import plan_night_routine


class HAStateClient(Protocol):
    async def get_state(self, entity_id: str) -> dict[str, Any]: ...


class ContextBuilder:
    """Build a compact `now.json` context from the HA entity contract.

    Home Assistant remains the source of truth. This builder only reads HA states
    declared in `entity_contract.yaml` and combines them with trusted semantic
    events already written to the event ledger.
    """

    def __init__(
        self,
        *,
        ha: HAStateClient,
        entity_contract: Mapping[str, Any],
        event_dir: str | Path,
        output_path: str | Path,
    ) -> None:
        self.ha = ha
        self.entity_contract = dict(entity_contract)
        self.event_dir = Path(event_dir)
        self.output_path = Path(output_path)

    @classmethod
    def from_yaml(
        cls,
        *,
        ha: HAStateClient,
        entity_contract_path: str | Path,
        event_dir: str | Path,
        output_path: str | Path,
    ) -> "ContextBuilder":
        with Path(entity_contract_path).open("r", encoding="utf-8") as f:
            contract = yaml.safe_load(f) or {}
        return cls(ha=ha, entity_contract=contract, event_dir=event_dir, output_path=output_path)

    async def build_now(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        context: dict[str, Any] = {
            "date": now.date().isoformat(),
            "time": now.isoformat(),
            "health": await self._read_flat_section("health"),
            "environment": await self._read_flat_section("environment"),
            "computer": await self._read_flat_section("computer"),
            "presence": await self._read_flat_section("presence"),
            "routines": await self._read_flat_section("routines"),
            "supplements": await self._read_supplements(),
            "events_today": self._read_events_for_date(now.date().isoformat()),
        }
        context["recommended_actions"] = plan_night_routine(context, now=now)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return context

    async def _read_flat_section(self, section: str) -> dict[str, Any]:
        spec = self.entity_contract.get(section) or {}
        if not isinstance(spec, Mapping):
            return {}
        result: dict[str, Any] = {}
        for key, entity_id in spec.items():
            if isinstance(entity_id, str):
                result[key] = await self._read_entity_value(entity_id)
        return result

    async def _read_supplements(self) -> dict[str, str]:
        supplements = self.entity_contract.get("supplements") or {}
        if not isinstance(supplements, Mapping):
            return {}
        result: dict[str, str] = {}
        for supplement_id, spec in supplements.items():
            if not isinstance(spec, Mapping):
                continue
            taken_entity = spec.get("taken_today")
            if not isinstance(taken_entity, str):
                continue
            state = await self._read_entity_value(taken_entity)
            if state == "on":
                result[str(supplement_id)] = "taken"
            elif state == "off":
                result[str(supplement_id)] = "missing"
            else:
                result[str(supplement_id)] = "unavailable"
        return result

    async def _read_entity_value(self, entity_id: str) -> Any:
        try:
            state = await self.ha.get_state(entity_id)
        except Exception:
            return "unavailable"
        return _coerce_state_value(state.get("state"))

    def _read_events_for_date(self, date_str: str) -> list[dict[str, Any]]:
        path = self.event_dir / f"{date_str}.jsonl"
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(json.loads(line))
        return events


def _coerce_state_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped == "":
        return stripped
    try:
        number = float(stripped)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number

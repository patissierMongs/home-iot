"""Runtime wiring for HA semantic events.

This layer connects three responsibilities:
1. Extract HA `state_changed` transitions.
2. Map them to trusted semantic events.
3. Persist them and optionally reflect derived helper state back into HA.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import yaml

from .events import EventLedger, SemanticEvent
from .semantic import SemanticEventMapper


class HAServiceClient(Protocol):
    async def call_service(
        self,
        domain: str,
        service: str,
        target: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...


class SemanticEventRuntime:
    """Handle HA events and persist/apply their semantic meaning."""

    def __init__(self, mapper: SemanticEventMapper, ledger: EventLedger, ha: HAServiceClient) -> None:
        self.mapper = mapper
        self.ledger = ledger
        self.ha = ha

    @classmethod
    def from_config(
        cls,
        *,
        config: dict[str, Any],
        ledger_dir: str | Path,
        ha: HAServiceClient,
    ) -> "SemanticEventRuntime":
        return cls(SemanticEventMapper.from_config(config), EventLedger(ledger_dir), ha)

    @classmethod
    def from_yaml(
        cls,
        *,
        config_path: str | Path,
        ledger_dir: str | Path,
        ha: HAServiceClient,
    ) -> "SemanticEventRuntime":
        with Path(config_path).open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return cls.from_config(config=config, ledger_dir=ledger_dir, ha=ha)

    async def handle_ha_event(self, ha_event: dict[str, Any]) -> SemanticEvent | None:
        """Record/apply semantic meaning for one HA event, if configured."""
        if ha_event.get("event_type") != "state_changed":
            return None

        data = ha_event.get("data") or {}
        entity_id = data.get("entity_id")
        if not entity_id:
            return None

        old_state = _state_value(data.get("old_state"))
        new_state = _state_value(data.get("new_state"))
        if old_state == new_state:
            return None

        ts = _parse_time_fired(ha_event.get("time_fired"))
        semantic_event = self.mapper.map_state_changed(
            entity_id=entity_id,
            old_state=old_state,
            new_state=new_state,
            ts=ts,
        )
        if semantic_event is None:
            return None

        self.ledger.record(semantic_event)
        await self._apply_helpers(semantic_event)
        return semantic_event

    async def _apply_helpers(self, event: SemanticEvent) -> None:
        """Reflect selected semantic events into HA helpers.

        The helper entities remain in HA so dashboards/automations can use them.
        The agent only updates them after recording the semantic event.
        """
        if event.domain == "supplement" and event.type == "taken":
            taken_helper = event.metadata.get("taken_helper")
            if taken_helper:
                await self.ha.call_service(
                    "input_boolean",
                    "turn_on",
                    target={"entity_id": taken_helper},
                )

            last_taken_helper = event.metadata.get("last_taken_helper")
            if last_taken_helper:
                await self.ha.call_service(
                    "input_datetime",
                    "set_datetime",
                    target={"entity_id": last_taken_helper},
                    data={"datetime": event.ts.strftime("%Y-%m-%d %H:%M:%S")},
                )


def _state_value(state_obj: Any) -> str | None:
    if isinstance(state_obj, dict):
        return state_obj.get("state")
    return None


def _parse_time_fired(value: Any) -> datetime:
    if isinstance(value, str) and value:
        # HA emits ISO 8601 timestamps. Python accepts offsets, but not a trailing Z
        # before 3.11-compatible normalization.
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    return datetime.now(timezone.utc)

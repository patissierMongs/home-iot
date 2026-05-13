"""Map Home Assistant state changes into trusted semantic events.

This module deliberately does not infer sensor reality. Home Assistant owns all
hardware integrations, template sensors, and low-level detection. The mapper only
translates HA state transitions into life-domain events the agent can record and
reason about.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .events import SemanticEvent


class SemanticEventMapper:
    """Config-driven mapper from HA entity transitions to semantic events."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SemanticEventMapper":
        return cls(config)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SemanticEventMapper":
        with Path(path).open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return cls(config)

    def map_state_changed(
        self,
        *,
        entity_id: str,
        old_state: str | None,
        new_state: str | None,
        ts: datetime,
    ) -> SemanticEvent | None:
        """Return a semantic event for a HA state transition, or None."""
        return (
            self._map_supplement(entity_id, old_state, new_state, ts)
            or self._map_presence(entity_id, old_state, new_state, ts)
            or self._map_routine(entity_id, old_state, new_state, ts)
        )

    def _map_supplement(
        self,
        entity_id: str,
        old_state: str | None,
        new_state: str | None,
        ts: datetime,
    ) -> SemanticEvent | None:
        for supplement_id, spec in (self.config.get("supplements") or {}).items():
            if spec.get("present_entity") != entity_id:
                continue
            if [old_state, new_state] != list(spec.get("taken_transition") or []):
                return None
            return SemanticEvent(
                ts=ts,
                domain="supplement",
                type="taken",
                entity=supplement_id,
                source="home_assistant",
                source_entity=entity_id,
                old_state=old_state,
                new_state=new_state,
                trusted=bool(spec.get("trusted", True)),
                metadata={
                    "display_name": spec.get("display_name", supplement_id),
                    "taken_helper": spec.get("taken_helper"),
                    "last_taken_helper": spec.get("last_taken_helper"),
                    "once_per_day": bool(spec.get("once_per_day", True)),
                },
            )
        return None

    def _map_presence(
        self,
        entity_id: str,
        old_state: str | None,
        new_state: str | None,
        ts: datetime,
    ) -> SemanticEvent | None:
        for presence_id, spec in (self.config.get("presence") or {}).items():
            if spec.get("entity") != entity_id:
                continue
            transition = [old_state, new_state]
            if transition == list(spec.get("arrived_transition") or []):
                event_type = "arrived_home"
            elif transition == list(spec.get("left_transition") or []):
                event_type = "left_home"
            else:
                return None
            return SemanticEvent(
                ts=ts,
                domain="presence",
                type=event_type,
                entity=presence_id,
                source="home_assistant",
                source_entity=entity_id,
                old_state=old_state,
                new_state=new_state,
                trusted=bool(spec.get("trusted", True)),
            )
        return None

    def _map_routine(
        self,
        entity_id: str,
        old_state: str | None,
        new_state: str | None,
        ts: datetime,
    ) -> SemanticEvent | None:
        for routine_id, spec in (self.config.get("routines") or {}).items():
            if spec.get("done_entity") != entity_id:
                continue
            if [old_state, new_state] != list(spec.get("done_transition") or []):
                return None
            return SemanticEvent(
                ts=ts,
                domain="routine",
                type="done",
                entity=routine_id,
                source="home_assistant",
                source_entity=entity_id,
                old_state=old_state,
                new_state=new_state,
                trusted=bool(spec.get("trusted", True)),
            )
        return None

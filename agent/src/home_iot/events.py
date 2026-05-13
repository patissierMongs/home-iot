"""Semantic event model and durable JSONL ledger.

The agent records trusted life-domain events derived from Home Assistant state.
Home Assistant remains the source of truth; this ledger preserves the semantic
meaning the agent will use for context building, analytics, and reports.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SemanticEvent:
    """A trusted life-domain event derived from a HA state change."""

    ts: datetime
    domain: str
    type: str
    entity: str
    source: str = "home_assistant"
    source_entity: str | None = None
    old_state: str | None = None
    new_state: str | None = None
    value: Any | None = None
    trusted: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ts"] = self.ts.isoformat()
        return data


class EventLedger:
    """Append-only JSONL event ledger partitioned by event date."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def record(self, event: SemanticEvent) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / f"{event.ts.date().isoformat()}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            json.dump(event.to_dict(), f, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        return path

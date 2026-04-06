"""
결정론적 규칙 엔진 — 빠른 경로.

LLM으로 보내기 전 이벤트를 규칙 리스트와 매칭. 매칭되면 규칙의 action을 실행하고,
`consume=True` 규칙은 LLM 경로를 건너뜀. `consume=False` 규칙은 실행 후 이벤트가
LLM으로도 전달되어 에이전트가 추가 판단 가능.

규칙 정의 예:
    Rule(
        name="door_opened_at_night_turn_on_hallway",
        match=lambda e: e["event_type"] == "state_changed"
                        and e["data"]["entity_id"] == "binary_sensor.jib_mun_door"
                        and e["data"]["new_state"]["state"] == "on",
        action=lambda tools: tools.ha_call_service("light", "turn_on", "light.hallway"),
        consume=True,
    )
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from .tools import Tools

log = structlog.get_logger(__name__)

EventDict = dict[str, Any]
MatchFn = Callable[[EventDict], bool]
ActionFn = Callable[[Tools, EventDict], Awaitable[Any]]


@dataclass
class Rule:
    name: str
    match: MatchFn
    action: ActionFn
    consume: bool = True


class RuleEngine:
    def __init__(self, tools: Tools, rules: list[Rule] | None = None) -> None:
        self.tools = tools
        self.rules: list[Rule] = rules or []

    def add(self, rule: Rule) -> None:
        self.rules.append(rule)

    async def dispatch(self, event: EventDict) -> bool:
        """
        이벤트를 규칙에 돌려봄.

        Returns: True면 이벤트 소비됨(LLM 불필요), False면 LLM이 이어받아야 함.
        """
        consumed = False
        for rule in self.rules:
            try:
                if rule.match(event):
                    log.info("rule.matched", rule=rule.name)
                    await rule.action(self.tools, event)
                    if rule.consume:
                        consumed = True
            except Exception as e:
                log.error("rule.error", rule=rule.name, error=str(e))
        return consumed


# --- 초기에는 규칙 없이 시작. 추후 이 리스트에 추가 ---
DEFAULT_RULES: list[Rule] = []

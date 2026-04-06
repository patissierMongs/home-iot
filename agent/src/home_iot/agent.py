"""
에이전트 루프 — HA 이벤트를 구독하고 규칙 엔진 + LLM 경로로 처리.

흐름:
    HA event → RuleEngine.dispatch → (consumed? done)
                                   → (not consumed, and "notable"?) → LLM.chat(think-about-this)
                                   → (else) ignore

초기에는 "notable" 필터를 보수적으로 두고(도어 센서 변화, presence 변화 등),
운용하며 LLM을 깨울 이벤트 종류를 점진적으로 확장.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from .bridges.activitywatch import ActivityWatchBridge
from .ha import HAClient
from .llm import LLM
from .rules import RuleEngine
from .tools import Tools

log = structlog.get_logger(__name__)


SYSTEM_PROMPT = """\
You are a local home-automation assistant for a Korean user's one-room apartment.
You read state from Home Assistant, call tools to control devices when needed,
and continuously learn to understand this home and its occupant better over time.

## 1. Gather context before deciding
- **Your first tool call should be `get_home_context()`**. It returns the home layout,
  device quirks, user habits, safety boundaries, and all previously-learned
  observations/preferences/patterns. Never guess from entity_id alone.
- Supplement with `ha_get_state` / `query_influx` / `get_recent_activity` as needed
  for current state.

## 2. Learning loop — ask when uncertain, record answers
- If an entity's meaning / location / purpose is unclear:
  (a) If you are talking to the user right now, ask directly. As soon as you get
      the answer, call `update_entity_dictionary` to persist it.
  (b) If asking now would derail the task, call `add_open_question` to queue it.
- When the user mentions a preference or habit, call `record_preference`.
- When analysis surfaces a reusable fact, call `record_observation`.
- At conversation start, call `list_open_questions` — raise pending questions when
  the timing is natural, not as an interrogation.

## 3. Control principles
- You only see events that the deterministic rule engine did not handle —
  these are ambiguous situations that need judgment.
- Sensitive actions (door locks, fingerbot triggers, large-scale device off,
  anything listed under safety_boundaries.require_approval) must go through
  `request_approval` first.
- Explain your reasoning briefly and concretely before each action.
- If unsure, do not act — answer "observing" or add an open question.
- Do not toggle the same device multiple times in a short window.

## 4. Language
- The user communicates in Korean. Your final user-facing responses are in Korean.
- Tool names, parameters, entity_ids stay as-is.
- Internal reasoning (thinking mode) can be in whatever language you prefer.

## 5. Persistence awareness
- Your `record_*` / `update_*` / `answer_question` tool calls persist to YAML files
  that outlive this conversation, this session, and even survive across different
  LLMs — the next Claude session and the 24/7 Nemotron agent both read the same
  files via `get_home_context`.
- Today's learning reaches tomorrow's you. Be accurate.
"""


class Agent:
    def __init__(self, enable_llm: bool = True, enable_aw: bool = True) -> None:
        self.ha = HAClient()
        self.tools = Tools(self.ha)
        self.rules = RuleEngine(self.tools)
        self.llm = LLM(self.tools) if enable_llm else None
        self.aw = ActivityWatchBridge() if enable_aw else None
        self._enable_llm = enable_llm

    async def aclose(self) -> None:
        await self.ha.aclose()
        if self.llm:
            await self.llm.aclose()
        if self.aw:
            await self.aw.aclose()

    def _is_notable(self, event: dict[str, Any]) -> bool:
        """
        어떤 이벤트를 LLM에 보낼지 필터.
        초기 기준: binary_sensor / person / device_tracker 상태 변화만.
        """
        if event.get("event_type") != "state_changed":
            return False
        data = event.get("data", {})
        entity_id: str = data.get("entity_id", "")
        old = (data.get("old_state") or {}).get("state")
        new = (data.get("new_state") or {}).get("state")
        if old == new:
            return False
        return entity_id.startswith(("binary_sensor.", "person.", "device_tracker."))

    async def handle_event(self, event: dict[str, Any]) -> None:
        consumed = await self.rules.dispatch(event)
        if consumed:
            return
        if not self._enable_llm or self.llm is None:
            return
        if not self._is_notable(event):
            return

        data = event["data"]
        entity_id = data["entity_id"]
        new_state = (data.get("new_state") or {}).get("state")
        fname = (data.get("new_state") or {}).get("attributes", {}).get("friendly_name", entity_id)

        user_msg = (
            f"이벤트: 엔티티 `{entity_id}` ({fname}) 상태가 `{new_state}`(으)로 변경되었습니다.\n"
            f"이 상황에서 어떤 조치가 필요한지 판단하세요. 필요 없다면 '조치 없음'이라고만 답하세요."
        )
        try:
            reply = await self.llm.chat(SYSTEM_PROMPT, user_msg, max_iterations=5)
            log.info("agent.llm_reply", entity=entity_id, reply=reply[:200])
        except Exception as e:
            log.error("agent.llm_error", error=str(e))

    async def _ha_event_loop(self) -> None:
        async for event in self.ha.stream_events(["state_changed"]):
            asyncio.create_task(self.handle_event(event))

    async def run(self) -> None:
        log.info("agent.starting", llm=self._enable_llm, aw=self.aw is not None)
        tasks = [asyncio.create_task(self._ha_event_loop(), name="ha_events")]
        if self.aw:
            tasks.append(asyncio.create_task(self.aw.run(), name="aw_bridge"))
        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
            await self.aclose()

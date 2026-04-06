"""
LLM 어댑터 — Ollama native API (tool calling 지원).

메시지 루프: 사용자/이벤트 메시지 → LLM → tool_calls → Tools.dispatch → LLM → ... → final answer.
Thinking 모드 지원(Nemotron-Cascade-2): options.thinking=true로 CoT 활성화.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from .config import settings
from .tools import TOOL_SCHEMAS, Tools

log = structlog.get_logger(__name__)


class LLM:
    def __init__(self, tools: Tools, model: str | None = None, thinking: bool = False) -> None:
        self.tools = tools
        self.model = model or settings.ollama_main_model
        self.thinking = thinking
        self._http = httpx.AsyncClient(base_url=settings.ollama_url, timeout=180.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def chat(
        self,
        system: str,
        user: str,
        max_iterations: int = 10,
    ) -> str:
        """
        Tool-calling 포함 완전한 대화 한 턴.

        system/user 메시지로 시작해서 모델이 도구를 호출할 때마다 결과를 다시 넣고
        최종 텍스트가 나올 때까지 반복.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        for iteration in range(max_iterations):
            options: dict[str, Any] = {}
            if self.thinking:
                options["thinking"] = True

            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "tools": TOOL_SCHEMAS,
                "options": options,
            }

            resp = await self._http.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            msg = data["message"]

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                # 최종 응답
                log.info("llm.final", iter=iteration, content_len=len(msg.get("content", "")))
                return msg.get("content", "")

            # Tool call 실행
            messages.append(msg)  # assistant의 tool_calls 응답을 히스토리에 추가
            for call in tool_calls:
                fn = call["function"]
                name = fn["name"]
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)
                log.info("llm.tool_call", name=name, args=args)
                try:
                    result = await self.tools.dispatch(name, args)
                except Exception as e:
                    result = {"error": str(e)}
                    log.error("llm.tool_error", name=name, error=str(e))
                messages.append(
                    {
                        "role": "tool",
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        log.warning("llm.max_iterations_reached")
        return "[에이전트가 최대 반복 횟수에 도달했습니다]"

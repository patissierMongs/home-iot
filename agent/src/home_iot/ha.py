"""
Home Assistant 클라이언트 — REST + WebSocket.

두 가지 모드 제공:
- REST: 단발성 호출 (상태 조회, 서비스 호출)
- WebSocket: 실시간 이벤트 구독 (state_changed 등)
"""
from __future__ import annotations

import asyncio
import itertools
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import structlog
import websockets

from .config import settings

log = structlog.get_logger(__name__)


class HAClient:
    """HA REST + WebSocket 통합 클라이언트."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.ha_url,
            headers={"Authorization": f"Bearer {settings.ha_token}"},
            timeout=10.0,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # ---------- REST ----------

    async def get_states(self, domain: str | None = None) -> list[dict[str, Any]]:
        """모든 엔티티 상태. domain 지정 시 필터링."""
        resp = await self._http.get("/api/states")
        resp.raise_for_status()
        states = resp.json()
        if domain:
            states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]
        return states

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        resp = await self._http.get(f"/api/states/{entity_id}")
        resp.raise_for_status()
        return resp.json()

    async def call_service(
        self,
        domain: str,
        service: str,
        target: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """HA 서비스 호출. 예: call_service('light', 'turn_on', target={'entity_id': 'light.x'})."""
        payload: dict[str, Any] = {}
        if target:
            payload.update(target)
        if data:
            payload.update(data)
        resp = await self._http.post(f"/api/services/{domain}/{service}", json=payload)
        resp.raise_for_status()
        return resp.json()

    # ---------- WebSocket ----------

    async def stream_events(
        self, event_types: list[str] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """
        WebSocket API로 HA 이벤트 스트리밍.

        Yields each event as a dict. Reconnects on disconnect.
        """
        ws_url = settings.ha_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/api/websocket"
        msg_id = itertools.count(1)

        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20) as ws:
                    # Auth handshake
                    hello = json.loads(await ws.recv())
                    assert hello["type"] == "auth_required"
                    await ws.send(json.dumps({"type": "auth", "access_token": settings.ha_token}))
                    auth_ok = json.loads(await ws.recv())
                    if auth_ok["type"] != "auth_ok":
                        raise RuntimeError(f"HA WS auth failed: {auth_ok}")
                    log.info("ha.ws.connected", version=auth_ok.get("ha_version"))

                    # Subscribe
                    types = event_types or ["state_changed"]
                    for t in types:
                        await ws.send(
                            json.dumps(
                                {"id": next(msg_id), "type": "subscribe_events", "event_type": t}
                            )
                        )

                    # Stream
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("type") == "event":
                            yield msg["event"]
            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                log.warning("ha.ws.disconnected", error=str(e))
                await asyncio.sleep(3)

    # ---------- 편의 메서드 ----------

    async def list_entities(self, domain: str | None = None) -> list[dict[str, str]]:
        """엔티티 목록을 간단한 형태로 (entity_id, friendly_name, state)."""
        states = await self.get_states(domain)
        return [
            {
                "entity_id": s["entity_id"],
                "friendly_name": s["attributes"].get("friendly_name", s["entity_id"]),
                "state": s["state"],
                "device_class": s["attributes"].get("device_class", ""),
                "unit": s["attributes"].get("unit_of_measurement", ""),
            }
            for s in states
        ]

    async def delete_config_entry(self, entry_id: str) -> bool:
        """WebSocket으로 config entry 삭제 (Awair 같은 찌꺼기 통합 제거용)."""
        ws_url = settings.ha_url.replace("http://", "ws://").replace("https://", "wss://")
        async with websockets.connect(f"{ws_url}/api/websocket") as ws:
            await ws.recv()  # auth_required
            await ws.send(json.dumps({"type": "auth", "access_token": settings.ha_token}))
            await ws.recv()  # auth_ok
            await ws.send(
                json.dumps({"id": 1, "type": "config_entries/remove", "entry_id": entry_id})
            )
            result = json.loads(await ws.recv())
            return bool(result.get("success"))

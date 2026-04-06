"""
Hue Bridge -> Local MQTT Bridge

Hue CLIP v2 API의 SSE 스트림을 구독해서 실시간 이벤트를 MQTT로 publish하고,
MQTT `.../set` 토픽을 subscribe해서 조명 제어 명령을 Hue로 전달합니다.

토픽 구조:
  home-iot/hue/light/{id}/state   (publish, retained)
  home-iot/hue/light/{id}/set     (subscribe)
"""
import json
import logging
import threading
import requests
import urllib3

from config.settings import (
    HUE_BRIDGE_IP,
    HUE_USERNAME,
    HUE_TOPIC_BASE,
)
from utils.mqtt_client import create_client, publish_json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)


class HueBridge:
    def __init__(self):
        if not HUE_USERNAME:
            raise RuntimeError("HUE_USERNAME 없음. setup_hue.py 먼저 실행하세요.")

        self.base_url = f"https://{HUE_BRIDGE_IP}/clip/v2"
        self.headers = {"hue-application-key": HUE_USERNAME}
        self.mqtt = create_client("hue-bridge")
        self.devices: dict[str, dict] = {}  # rid -> metadata
        self._stop = threading.Event()

    # ---------- REST ----------

    def _get(self, path: str) -> dict:
        resp = requests.get(
            f"{self.base_url}{path}",
            headers=self.headers,
            verify=False,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, body: dict) -> dict:
        resp = requests.put(
            f"{self.base_url}{path}",
            headers=self.headers,
            json=body,
            verify=False,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_initial_state(self):
        """브릿지의 모든 조명 초기 상태를 가져와서 캐시 + publish."""
        data = self._get("/resource/light")
        for light in data.get("data", []):
            rid = light["id"]
            name = light.get("metadata", {}).get("name", rid)
            self.devices[rid] = {"name": name, "type": "light"}
            self._publish_light_state(rid, light)
            logger.info(f"Light 등록: {name} ({rid})")

    def _publish_light_state(self, rid: str, light: dict):
        state = {
            "name": self.devices.get(rid, {}).get("name"),
            "on": light.get("on", {}).get("on"),
            "brightness": light.get("dimming", {}).get("brightness"),
        }
        color = light.get("color", {}).get("xy")
        if color:
            state["color_xy"] = color
        ct = light.get("color_temperature", {}).get("mirek")
        if ct is not None:
            state["color_temp_mirek"] = ct

        topic = f"{HUE_TOPIC_BASE}/light/{rid}/state"
        self.mqtt.publish(topic, json.dumps(state), qos=1, retain=True)

    # ---------- SSE (실시간 이벤트) ----------

    def stream_events(self):
        """CLIP v2 eventstream SSE를 구독."""
        url = f"https://{HUE_BRIDGE_IP}/eventstream/clip/v2"
        headers = {**self.headers, "Accept": "text/event-stream"}

        logger.info("SSE 스트림 연결 중...")
        with requests.get(url, headers=headers, verify=False, stream=True, timeout=None) as resp:
            for line in resp.iter_lines(decode_unicode=True):
                if self._stop.is_set():
                    break
                if not line or not line.startswith("data:"):
                    continue
                try:
                    events = json.loads(line[5:].strip())
                    for event in events:
                        self._handle_event(event)
                except json.JSONDecodeError:
                    logger.warning(f"SSE JSON 파싱 실패: {line[:100]}")

    def _handle_event(self, event: dict):
        """SSE 이벤트 처리 - update 이벤트의 각 리소스 변화를 MQTT로 publish."""
        if event.get("type") != "update":
            return
        for item in event.get("data", []):
            if item.get("type") == "light":
                rid = item["id"]
                # 증분 업데이트를 병합하기보다는 해당 라이트만 다시 GET
                try:
                    light = self._get(f"/resource/light/{rid}")["data"][0]
                    self._publish_light_state(rid, light)
                except Exception as e:
                    logger.error(f"라이트 재조회 실패 {rid}: {e}")

    # ---------- MQTT → Hue (제어) ----------

    def on_mqtt_message(self, client, userdata, msg):
        """MQTT .../set 토픽에서 들어온 명령을 Hue API로 전달."""
        # 토픽: home-iot/hue/light/{rid}/set
        parts = msg.topic.split("/")
        if len(parts) != 5 or parts[4] != "set":
            return

        rid = parts[3]
        try:
            command = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            logger.error(f"set 페이로드 JSON 파싱 실패: {msg.payload}")
            return

        body = {}
        if "on" in command:
            body["on"] = {"on": bool(command["on"])}
        if "brightness" in command:
            body["dimming"] = {"brightness": float(command["brightness"])}
        if "color_temp_mirek" in command:
            body["color_temperature"] = {"mirek": int(command["color_temp_mirek"])}
        if "color_xy" in command:
            xy = command["color_xy"]
            body["color"] = {"xy": {"x": xy[0], "y": xy[1]}}

        if not body:
            logger.warning(f"유효한 명령 없음: {command}")
            return

        try:
            self._put(f"/resource/light/{rid}", body)
            logger.info(f"제어 성공: {rid} ← {command}")
        except Exception as e:
            logger.error(f"제어 실패 {rid}: {e}")

    def run(self):
        self.fetch_initial_state()

        # MQTT set 토픽 구독
        self.mqtt.on_message = self.on_mqtt_message
        self.mqtt.subscribe(f"{HUE_TOPIC_BASE}/light/+/set", qos=1)
        self.mqtt.loop_start()

        # SSE 스트림 (블로킹)
        try:
            self.stream_events()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self._stop.set()
        self.mqtt.loop_stop()
        self.mqtt.disconnect()

"""
Qingping Cloud API -> MQTT bridge.

Polls the Qingping Developer API every 15 minutes (matching device report_interval),
publishes sensor data to MQTT for HA consumption.

MQTT topics (HA auto-discovery compatible):
  homeassistant/sensor/qingping_{mac}_{metric}/config  (discovery)
  qingping/{mac}/state                                  (state)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

OAUTH_URL = "https://oauth.cleargrass.com/oauth2/token"
DEVICES_URL = "https://apis.cleargrass.com/v1/apis/devices"
POLL_INTERVAL = 900  # 15 minutes (matches device report_interval)


class QingpingBridge:
    def __init__(self, app_key: str, app_secret: str, mqtt_publish_fn=None):
        self.app_key = app_key
        self.app_secret = app_secret
        self._token = ""
        self._token_expires = 0
        self._http = httpx.AsyncClient(timeout=15.0)
        self._mqtt_publish = mqtt_publish_fn  # async fn(topic, payload)

    async def aclose(self):
        await self._http.aclose()

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token
        resp = await self._http.post(
            OAUTH_URL,
            auth=(self.app_key, self.app_secret),
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        d = resp.json()
        self._token = d["access_token"]
        self._token_expires = time.time() + d.get("expires_in", 7200) - 60
        log.info("qingping.token_refreshed")
        return self._token

    async def get_devices(self) -> list[dict[str, Any]]:
        token = await self._get_token()
        resp = await self._http.get(
            DEVICES_URL,
            headers={"Authorization": "Bearer " + token},
            params={"timestamp": str(int(time.time() * 1000))},
        )
        resp.raise_for_status()
        return resp.json().get("devices", [])

    async def poll_and_publish(self):
        try:
            devices = await self.get_devices()
            for dev in devices:
                info = dev.get("info", {})
                data = dev.get("data", {})
                mac = info.get("mac", "unknown")
                name = info.get("name", "Qingping")

                state = {}
                for key in ("temperature", "humidity", "co2", "pm25", "pm10", "tvoc_index", "noise", "battery"):
                    if key in data:
                        state[key] = data[key].get("value")

                if self._mqtt_publish and state:
                    # Publish state
                    topic = "qingping/" + mac + "/state"
                    await self._mqtt_publish(topic, json.dumps(state))

                    # HA MQTT auto-discovery
                    await self._publish_discovery(mac, name, state)

                log.info("qingping.polled", mac=mac, metrics=len(state),
                         co2=state.get("co2"), pm25=state.get("pm25"),
                         temp=state.get("temperature"), humid=state.get("humidity"))
        except Exception as e:
            log.error("qingping.poll_error", error=str(e))

    async def _publish_discovery(self, mac: str, name: str, state: dict):
        metrics = {
            "temperature": {"unit": "\u00b0C", "dc": "temperature", "icon": "mdi:thermometer"},
            "humidity": {"unit": "%", "dc": "humidity", "icon": "mdi:water-percent"},
            "co2": {"unit": "ppm", "dc": "carbon_dioxide", "icon": "mdi:molecule-co2"},
            "pm25": {"unit": "\u00b5g/m\u00b3", "dc": "pm25", "icon": "mdi:blur"},
            "pm10": {"unit": "\u00b5g/m\u00b3", "dc": "pm10", "icon": "mdi:blur-linear"},
            "tvoc_index": {"unit": "", "dc": None, "icon": "mdi:air-filter"},
            "noise": {"unit": "dB", "dc": None, "icon": "mdi:volume-high"},
            "battery": {"unit": "%", "dc": "battery", "icon": "mdi:battery"},
        }
        for key, cfg in metrics.items():
            if key not in state:
                continue
            uid = "qingping_" + mac.lower() + "_" + key
            disc = {
                "name": name + " " + key.replace("_", " ").title(),
                "unique_id": uid,
                "state_topic": "qingping/" + mac + "/state",
                "value_template": "{{ value_json." + key + " }}",
                "unit_of_measurement": cfg["unit"],
                "icon": cfg["icon"],
                "device": {
                    "identifiers": ["qingping_" + mac],
                    "name": name,
                    "manufacturer": "Qingping",
                    "model": "Air Monitor",
                },
            }
            if cfg["dc"]:
                disc["device_class"] = cfg["dc"]
                disc["state_class"] = "measurement"

            topic = "homeassistant/sensor/" + uid + "/config"
            await self._mqtt_publish(topic, json.dumps(disc))

    async def run(self):
        log.info("qingping.bridge.starting", interval=POLL_INTERVAL)
        while True:
            await self.poll_and_publish()
            await asyncio.sleep(POLL_INTERVAL)


async def main():
    """Standalone test."""
    import os
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[structlog.processors.add_log_level, structlog.processors.TimeStamper(fmt="iso"),
                    structlog.dev.ConsoleRenderer()],
    )

    key = os.environ.get("QINGPING_APP_KEY", "_sL3qptvR")
    secret = os.environ.get("QINGPING_APP_SECRET", "cef89be82fd111f1858c52540055385a")

    import paho.mqtt.client as mqtt
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="qingping-bridge")
    client.connect("localhost", 1883)
    client.loop_start()

    async def pub(topic, payload):
        client.publish(topic, payload, retain=True)

    bridge = QingpingBridge(key, secret, pub)
    await bridge.poll_and_publish()
    print("First poll done. Check MQTT.")
    await bridge.aclose()
    client.loop_stop()


if __name__ == "__main__":
    asyncio.run(main())

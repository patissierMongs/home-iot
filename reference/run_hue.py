#!/usr/bin/env python3
"""Hue Bridge 실행 - SSE 실시간 이벤트 → MQTT, MQTT set → Hue 제어."""
import logging
from bridges.hue_bridge import HueBridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

if __name__ == "__main__":
    HueBridge().run()

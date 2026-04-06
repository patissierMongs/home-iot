#!/usr/bin/env python3
"""콘솔 모니터 실행 - MQTT 토픽을 구독하고 실시간 출력."""
import logging

from subscribers.console_logger import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

if __name__ == "__main__":
    run()

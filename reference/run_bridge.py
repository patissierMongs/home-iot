#!/usr/bin/env python3
"""
테스트용 - 더미 Qingping 데이터를 MQTT로 publish.
실제 기기 연결 전 동작 확인용.
"""
import json
import time
import random
import logging

from utils.mqtt_client import create_client, publish_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

FAKE_MAC = "AABBCCDDEEFF"


def generate_fake_data():
    return {
        "temperature": round(random.uniform(20, 28), 1),
        "humidity": round(random.uniform(40, 70), 1),
        "co2": random.randint(400, 1200),
        "pm25": random.randint(5, 80),
        "pm10": random.randint(10, 120),
        "tvoc": round(random.uniform(0.1, 2.0), 2),
    }


if __name__ == "__main__":
    client = create_client("fake-qingping")
    client.loop_start()

    topic = f"qingping/{FAKE_MAC}/up"
    print(f"더미 데이터 publish 시작: {topic}")

    try:
        while True:
            data = generate_fake_data()
            publish_json(client, topic, data)
            print(f"  Published: {json.dumps(data)}")
            time.sleep(5)
    except KeyboardInterrupt:
        client.loop_stop()
        client.disconnect()
        print("\n종료")

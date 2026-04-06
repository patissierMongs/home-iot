"""
MQTT Subscriber - Qingping Air Monitor 2에서 직접 오는 센서 데이터를 실시간 출력.
토픽: qingping/{mac}/up
"""
import json
import logging
from datetime import datetime

from config.settings import QINGPING_TOPIC_UP
from utils.mqtt_client import create_client

logger = logging.getLogger(__name__)

# 센서 표시 설정
SENSOR_DISPLAY = {
    "temperature": ("온도", "C"),
    "humidity": ("습도", "%"),
    "co2": ("CO2", "ppm"),
    "pm25": ("PM2.5", "ug/m3"),
    "pm10": ("PM10", "ug/m3"),
    "tvoc": ("tVOC", "mg/m3"),
}


def on_message(client, userdata, msg):
    """MQTT 메시지 수신 콜백."""
    try:
        raw = msg.payload.decode()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{'='*50}")
        print(f"  [{ts}] Topic: {msg.topic}")
        print(f"{'='*50}")

        # Qingping 기기의 실제 payload 형식에 따라 파싱
        try:
            data = json.loads(raw)
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            # JSON이 아닌 경우 raw 출력
            print(f"  Raw: {raw}")

        print()

    except Exception as e:
        logger.error(f"메시지 처리 오류: {e}")


def run():
    """Qingping 토픽을 구독하고 콘솔에 출력."""
    client = create_client("console-logger")
    client.on_message = on_message

    # qingping/+/up : 모든 Qingping 기기의 업링크 메시지 수신
    client.subscribe(QINGPING_TOPIC_UP, qos=1)
    logger.info(f"Subscribed to: {QINGPING_TOPIC_UP}")

    # 추후 다른 기기 토픽도 여기서 구독 추가 가능
    # client.subscribe("home-iot/#", qos=1)

    print(f"[Console Logger] {QINGPING_TOPIC_UP} 구독 중... (Ctrl+C로 종료)")
    client.loop_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()

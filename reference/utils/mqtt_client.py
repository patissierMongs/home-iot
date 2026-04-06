import json
import logging
from paho.mqtt import client as mqtt_client

from config.settings import MQTT_BROKER_HOST, MQTT_BROKER_PORT

logger = logging.getLogger(__name__)


def create_client(client_id: str) -> mqtt_client.Client:
    """MQTT 클라이언트 생성 및 브로커 연결."""
    client = mqtt_client.Client(
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
        client_id=client_id,
    )

    def on_connect(client, userdata, flags, rc, properties):
        if rc == 0:
            logger.info(f"MQTT 브로커 연결 성공 ({MQTT_BROKER_HOST}:{MQTT_BROKER_PORT})")
        else:
            logger.error(f"MQTT 연결 실패, code: {rc}")

    def on_disconnect(client, userdata, flags, rc, properties):
        logger.warning(f"MQTT 연결 끊김, code: {rc}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT)
    return client


def publish_json(client: mqtt_client.Client, topic: str, data: dict):
    """JSON 데이터를 MQTT 토픽에 publish."""
    payload = json.dumps(data, ensure_ascii=False)
    result = client.publish(topic, payload, qos=1)
    if result.rc == 0:
        logger.debug(f"Published to {topic}")
    else:
        logger.error(f"Publish 실패: {topic}, rc={result.rc}")

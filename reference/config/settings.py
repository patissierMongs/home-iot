import os
from dotenv import load_dotenv

load_dotenv()

# MQTT Broker
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))

# Qingping (self-built MQTT - deferred)
QINGPING_TOPIC_UP = "qingping/+/up"
QINGPING_TOPIC_DOWN = "qingping/{mac}/down"

# Hue Bridge
HUE_BRIDGE_IP = os.getenv("HUE_BRIDGE_IP", "")
HUE_USERNAME = os.getenv("HUE_USERNAME", "")
HUE_CLIENTKEY = os.getenv("HUE_CLIENTKEY", "")

# SmartThings
SMARTTHINGS_PAT = os.getenv("SMARTTHINGS_PAT", "")
SMARTTHINGS_POLL_INTERVAL = int(os.getenv("SMARTTHINGS_POLL_INTERVAL", 30))

# Topic convention: home-iot/{integration}/{device_type}/{id}/{state|set}
TOPIC_PREFIX = "home-iot"
HUE_TOPIC_BASE = f"{TOPIC_PREFIX}/hue"
SMARTTHINGS_TOPIC_BASE = f"{TOPIC_PREFIX}/smartthings"

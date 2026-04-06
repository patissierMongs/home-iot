"""
home-iot Desktop Audio Player
=============================

Long-running daemon that listens on an MQTT topic and plays audio on the
Windows desktop. Two message types:

  1) {"text": "안녕하세요", "voice": "Hanna", "priority": "normal"}
     -> Calls ElevenLabs TTS, caches mp3, plays.

  2) {"url": "https://.../file.mp3"} or {"file": "C:/path/file.mp3"}
     -> Downloads (if url) then plays.

Topic: home-iot/audio/speak  (configurable via HOME_IOT_AUDIO_TOPIC env)

Run on the Windows host (not WSL). Uses the default Windows audio output
device via the `miniaudio` Python binding, which supports mp3 natively and
does not require ffmpeg.

Install (Windows PowerShell):
  pip install paho-mqtt httpx miniaudio

Start manually:
  python audio_player.py

Run at login (Windows):
  - Shortcut in  shell:startup  pointing at  pythonw audio_player.py
  - Or Task Scheduler with trigger "At log on"

Environment variables (all optional, sensible defaults):
  HOME_IOT_MQTT_HOST        default: 192.168.50.108 (WSL IP from Windows side)
  HOME_IOT_MQTT_PORT        default: 1883
  HOME_IOT_AUDIO_TOPIC      default: home-iot/audio/speak
  HOME_IOT_ELEVENLABS_KEY   required for TTS mode
  HOME_IOT_DEFAULT_VOICE    default: Hanna (will be resolved to voice_id)
  HOME_IOT_CACHE_DIR        default: %LOCALAPPDATA%\home-iot-audio\cache
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import miniaudio
import paho.mqtt.client as mqtt

# ----------------------------- Configuration -----------------------------

MQTT_HOST = os.environ.get("HOME_IOT_MQTT_HOST", "192.168.50.108")
MQTT_PORT = int(os.environ.get("HOME_IOT_MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("HOME_IOT_AUDIO_TOPIC", "home-iot/audio/speak")
MQTT_STATUS_TOPIC = os.environ.get("HOME_IOT_STATUS_TOPIC", "home-iot/audio/status")
MQTT_CLIENT_ID = os.environ.get("HOME_IOT_MQTT_CLIENT_ID", "desktop-audio-player")

ELEVENLABS_KEY = os.environ.get("HOME_IOT_ELEVENLABS_KEY", "")
DEFAULT_VOICE = os.environ.get("HOME_IOT_DEFAULT_VOICE", "Hanna")
ELEVENLABS_MODEL = os.environ.get("HOME_IOT_ELEVENLABS_MODEL", "eleven_v3")

# Voice settings chosen after A/B testing on 2026-04-06 with Hanna (Korean female).
# A = default v3 — picked by user as cleanest + most natural for home notifications.
DEFAULT_VOICE_SETTINGS: dict[str, Any] = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "use_speaker_boost": True,
}

# Fixed voice-name -> voice_id map for the voices we've already evaluated.
# Extend as needed, or override per-message via the "voice_id" field.
VOICE_IDS: dict[str, str] = {
    "Hanna": "zgDzx5jLLCqEp6Fl7Kl7",
    "Jisoo": "iWLjl1zCuqXRkW6494ve",
    "Jini": "0oqpliV6dVSr9XomngOW",
    "Adam": "pNInz6obpgDQGcFmaJgB",  # HA default, fallback
}

CACHE_DIR = Path(
    os.environ.get(
        "HOME_IOT_CACHE_DIR",
        str(Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache"))) / "home-iot-audio" / "cache"),
    )
)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("home-iot-audio")


# ----------------------------- Playback -----------------------------


_play_lock = threading.Lock()


def _play_mp3(path: Path) -> None:
    """Block until the mp3 finishes. Serialized via _play_lock."""
    with _play_lock:
        try:
            stream = miniaudio.stream_file(str(path))
            with miniaudio.PlaybackDevice() as device:
                device.start(stream)
                # Wait for stream to finish. miniaudio's stream_file returns a
                # generator; when exhausted, start() completes. Simplest wait:
                while device.running:
                    time.sleep(0.1)
        except Exception as e:
            log.error("playback failed: %s", e)


def _download(url: str) -> Path:
    """Download a remote URL to cache and return its local path."""
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    dest = CACHE_DIR / f"dl-{h}.mp3"
    if dest.exists():
        return dest
    with httpx.stream("GET", url, timeout=30.0) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(8192):
                f.write(chunk)
    return dest


def _synthesize(
    text: str,
    voice_id: str,
    model_id: str,
    voice_settings: dict[str, Any] | None = None,
) -> Path:
    """Call ElevenLabs TTS; return path to cached mp3. Cache key = hash of inputs."""
    if not ELEVENLABS_KEY:
        raise RuntimeError("HOME_IOT_ELEVENLABS_KEY env var not set")
    settings = voice_settings or DEFAULT_VOICE_SETTINGS
    settings_key = json.dumps(settings, sort_keys=True)
    key = hashlib.sha1(f"{voice_id}|{model_id}|{settings_key}|{text}".encode()).hexdigest()[:20]
    dest = CACHE_DIR / f"tts-{key}.mp3"
    if dest.exists():
        log.debug("cache hit: %s", dest.name)
        return dest
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    body = {"text": text, "model_id": model_id, "voice_settings": settings}
    headers = {"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"}
    with httpx.stream("POST", url, json=body, headers=headers, timeout=60.0) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(8192):
                f.write(chunk)
    log.info("synthesized %d chars -> %s", len(text), dest.name)
    return dest


# ----------------------------- Message handling -----------------------------


def _resolve_voice(msg: dict[str, Any]) -> str:
    """Resolve a message's voice field to a concrete ElevenLabs voice_id."""
    if vid := msg.get("voice_id"):
        return str(vid)
    name = str(msg.get("voice", DEFAULT_VOICE))
    if name in VOICE_IDS:
        return VOICE_IDS[name]
    log.warning("unknown voice name '%s', falling back to default", name)
    return VOICE_IDS[DEFAULT_VOICE]


def handle_message(client: mqtt.Client, payload: bytes) -> None:
    try:
        msg = json.loads(payload.decode("utf-8"))
    except Exception as e:
        log.error("invalid json: %s", e)
        return

    log.info("received: %s", {k: (str(v)[:80] if isinstance(v, str) else v) for k, v in msg.items()})
    client.publish(MQTT_STATUS_TOPIC, json.dumps({"state": "processing", "ts": time.time()}), retain=True)

    try:
        if text := msg.get("text"):
            voice_id = _resolve_voice(msg)
            model = msg.get("model", ELEVENLABS_MODEL)
            settings = msg.get("voice_settings")  # optional per-message override
            path = _synthesize(str(text), voice_id, model, settings)
        elif url := msg.get("url"):
            path = _download(str(url))
        elif file_path := msg.get("file"):
            path = Path(str(file_path))
            if not path.exists():
                raise FileNotFoundError(path)
        else:
            log.error("message missing 'text', 'url', or 'file'")
            return

        client.publish(MQTT_STATUS_TOPIC, json.dumps({"state": "playing", "file": path.name, "ts": time.time()}), retain=True)
        _play_mp3(path)
        client.publish(MQTT_STATUS_TOPIC, json.dumps({"state": "idle", "ts": time.time()}), retain=True)
    except Exception as e:
        log.exception("handle error")
        client.publish(MQTT_STATUS_TOPIC, json.dumps({"state": "error", "error": str(e), "ts": time.time()}), retain=True)


# ----------------------------- MQTT loop -----------------------------


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        log.info("connected to mqtt %s:%d", MQTT_HOST, MQTT_PORT)
        client.subscribe(MQTT_TOPIC, qos=1)
        log.info("subscribed to %s", MQTT_TOPIC)
        client.publish(MQTT_STATUS_TOPIC, json.dumps({"state": "idle", "ts": time.time()}), retain=True)
    else:
        log.error("mqtt connect failed rc=%s", rc)


def on_message(client, userdata, msg):
    # Do work in a background thread so the mqtt callback returns quickly.
    threading.Thread(target=handle_message, args=(client, msg.payload), daemon=True).start()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    log.info("starting home-iot desktop audio player")
    log.info("cache dir: %s", CACHE_DIR)

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=MQTT_CLIENT_ID,
    )
    # Last will so dashboards see when the player goes offline
    client.will_set(MQTT_STATUS_TOPIC, json.dumps({"state": "offline"}), retain=True)
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_forever()
        except KeyboardInterrupt:
            log.info("shutting down")
            client.publish(MQTT_STATUS_TOPIC, json.dumps({"state": "offline"}), retain=True)
            return
        except Exception as e:
            log.error("mqtt loop died: %s — reconnecting in 5s", e)
            time.sleep(5)


if __name__ == "__main__":
    main()

# home-iot desktop audio player

A tiny MQTT-subscribed audio daemon that runs on the Windows desktop and plays
TTS or arbitrary mp3 URLs for the home-iot agent to notify the user.

## Architecture

```
 any HA automation / agent / script
         │
         │  mqtt publish  home-iot/audio/speak
         │  {"text": "...", "voice": "Hanna"}
         ▼
 Mosquitto  (WSL, 192.168.50.108:1883)
         │
         │  subscribed
         ▼
 audio_player.py  ← runs on the Windows desktop
         │
         │  ElevenLabs REST
         ▼
 cached mp3  →  miniaudio  →  default Windows audio output
```

Status topic: `home-iot/audio/status` (retained)
- `{"state": "idle"}` — ready
- `{"state": "processing"}` — synthesizing / downloading
- `{"state": "playing", "file": "..."}` — currently playing
- `{"state": "error", "error": "..."}` — last operation failed
- `{"state": "offline"}` — (will) set by broker last-will when the player drops off

## Why this instead of HA's tts.speak?

HA's tts.speak service requires a `media_player` entity to target, and there is
no clean built-in way to expose the Windows desktop's default audio output as a
HA media_player. This daemon is the media_player — decoupled from HA so it can
also be driven directly from the agent daemon, the MQTT CLI, or ad-hoc scripts.

## Install

1. Copy the whole `desktop-audio-player/` folder to the Windows side, e.g.
   `C:\Users\upica\home-iot\desktop-audio-player\`.
2. Make sure Python 3.11+ is installed on Windows.
3. Copy `secrets.ps1.example` → `secrets.ps1` and fill in the API key.
4. First run: `.\start.ps1` — it creates a venv and installs deps automatically.
5. To run at login, either:
   - Place a shortcut to `start.ps1` in `shell:startup`, or
   - Register a Task Scheduler "at log on" task (one-liner in `start.ps1` header).

## Message schema

Publish JSON to `home-iot/audio/speak`:

```json
// TTS mode (most common)
{"text": "제습기를 가동해 주세요", "voice": "Hanna"}

// Explicit voice_id
{"text": "...", "voice_id": "zgDzx5jLLCqEp6Fl7Kl7"}

// Play a remote mp3
{"url": "http://192.168.50.108:8123/path/to/file.mp3"}

// Play a local file
{"file": "C:/Users/upica/Music/chime.mp3"}
```

## Known voices (extend `VOICE_IDS` in `audio_player.py`)

| Name  | Korean, female, age       | Use case             |
|-------|---------------------------|----------------------|
| Hanna | Seoul, young              | default, calm/clear  |
| Jisoo | Standard, young           | lively               |
| Jini  | Standard, middle-aged     | intellectual         |
| Adam  | English male (HA default) | fallback             |

## Troubleshooting

- No playback, no logs: check Windows Firewall isn't blocking outbound 1883 to
  the WSL IP.
- `cannot find mqtt host`: confirm WSL IP with `wsl hostname -I` on the Windows
  side, update `secrets.ps1` if needed.
- Audio stuttering: miniaudio uses WASAPI by default; confirm the default audio
  device in Windows sound settings is the one you expect.

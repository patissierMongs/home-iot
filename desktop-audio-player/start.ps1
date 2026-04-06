# home-iot desktop audio player - Windows launcher
# Place a shortcut to this script in:  shell:startup
# (Windows + R, then type "shell:startup")
#
# Or register with Task Scheduler for a "run at login, hidden" behavior:
#   schtasks /Create /SC ONLOGON /TN "home-iot-audio" `
#     /TR "powershell -NoProfile -WindowStyle Hidden -File C:\Users\upica\home-iot\desktop-audio-player\start.ps1" `
#     /RL HIGHEST

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# Secrets — the ElevenLabs API key is loaded from a sibling file so this .ps1
# can live in version control without leaking. Create `secrets.ps1` beside this
# script containing a single line:  $env:HOME_IOT_ELEVENLABS_KEY = 'sk_...'
if (Test-Path '.\secrets.ps1') { . .\secrets.ps1 }

# Default voice (override any time by writing a different value to secrets.ps1)
if (-not $env:HOME_IOT_DEFAULT_VOICE) { $env:HOME_IOT_DEFAULT_VOICE = 'Hanna' }

# Create venv if missing
if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
    Write-Host "Creating venv..."
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -U pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

& .\.venv\Scripts\python.exe audio_player.py

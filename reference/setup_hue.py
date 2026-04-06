#!/usr/bin/env python3
"""
Hue Bridge 초기 설정 - API 키(application key) 발급 헬퍼.

사용법:
  1. Hue Bridge 본체의 둥근 버튼을 누른다
  2. 30초 안에 이 스크립트를 실행한다
  3. 발급된 키가 .env 파일에 자동 저장된다
"""
import sys
import requests
import urllib3
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HUE_BRIDGE_IP = "192.168.50.205"
DEVICE_TYPE = "home-iot#wsl"

ENV_PATH = Path(__file__).parent / ".env"


def register():
    url = f"https://{HUE_BRIDGE_IP}/api"
    print(f"Hue Bridge({HUE_BRIDGE_IP})에 등록 요청 중...")
    print("→ 먼저 브릿지 본체의 둥근 버튼을 누르세요!")
    input("버튼을 누른 뒤 Enter...")

    resp = requests.post(
        url,
        json={"devicetype": DEVICE_TYPE, "generateclientkey": True},
        verify=False,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()[0]

    if "error" in data:
        err = data["error"]
        print(f"❌ 에러: {err.get('description')}")
        if err.get("type") == 101:
            print("   → 링크 버튼을 먼저 누른 뒤 다시 시도하세요.")
        sys.exit(1)

    success = data["success"]
    username = success["username"]
    clientkey = success.get("clientkey", "")

    print(f"\n✅ 발급 성공!")
    print(f"   username: {username}")

    # .env 파일에 append/update
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text().splitlines()
        lines = [l for l in lines if not l.startswith("HUE_")]

    lines.extend([
        f"HUE_BRIDGE_IP={HUE_BRIDGE_IP}",
        f"HUE_USERNAME={username}",
        f"HUE_CLIENTKEY={clientkey}",
    ])
    ENV_PATH.write_text("\n".join(lines) + "\n")
    print(f"   .env 저장 완료")


if __name__ == "__main__":
    register()

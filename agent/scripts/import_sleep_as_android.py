#!/usr/bin/env python3
"""Sleep as Android CSV 일회성 임포터 실행."""
import json
import sys
from pathlib import Path

from home_iot.importers.sleep_as_android import import_to_influx

DEFAULT_PATH = Path("/mnt/c/Users/upica/Downloads/Sleep as Android Data/sleep-export.csv")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    if not path.exists():
        print(f"❌ CSV 파일이 없습니다: {path}")
        sys.exit(1)
    print(f"📥 임포트 시작: {path}")
    stats = import_to_influx(path, include_actigraphy=True, include_events=True)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

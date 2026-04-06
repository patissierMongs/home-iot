#!/usr/bin/env python3
"""Samsung Health data export one-shot importer."""
import json
import logging
import sys
from pathlib import Path

from home_iot.importers.samsung_health import import_samsung_health

DEFAULT_PATH = Path("/mnt/c/Users/upica/Downloads")

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    # Find Samsung Health export (ZIP or directory)
    search = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    candidates = []
    if search.is_file():
        candidates = [search]
    else:
        # Look for common Samsung Health export patterns
        for pattern in ["*samsung*health*.zip", "*Samsung*Health*", "*samsunghealth*"]:
            candidates.extend(search.glob(pattern))
        if not candidates:
            # Also check for extracted directories
            for d in search.iterdir():
                if d.is_dir() and "samsung" in d.name.lower() and "health" in d.name.lower():
                    candidates.append(d)

    if not candidates:
        print(f"No Samsung Health export found in {search}")
        print("Usage: python import_samsung_health.py [path_to_zip_or_directory]")
        sys.exit(1)

    target = candidates[0]
    print(f"Importing from: {target}")
    stats = import_samsung_health(target, include_generic=True)
    print(json.dumps(stats, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

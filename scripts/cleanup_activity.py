from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_activity_events(storage_path: str) -> int:
    """Delete existing events whose tool_name contains '_SYNC' or whose params contain '\\\\Temp\\\\tmp'."""
    path = Path(storage_path)
    if not path.exists():
        logger.info("No activity file at %s", storage_path)
        return 0

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    original_count = len(data)
    filtered = []
    removed = 0

    for event in data:
        tool_name = event.get("tool_name", "")
        params = event.get("parameters", {})
        params_str = json.dumps(params)

        if "_SYNC" in tool_name or "\\\\Temp\\\\tmp" in params_str:
            removed += 1
            continue
        filtered.append(event)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    logger.info(
        "Cleaned %d events (from %d to %d)",
        removed,
        original_count,
        len(filtered),
    )
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean up local tool activity feed by removing _SYNC and temp events."
    )
    parser.add_argument(
        "--storage-path",
        default="./storage/activity/tool_events.json",
        help="Path to the tool_events.json file",
    )
    args = parser.parse_args()

    removed = cleanup_activity_events(args.storage_path)
    logger.info("Removed %d events", removed)
    return 0


if __name__ == "__main__":
    sys.exit(main())

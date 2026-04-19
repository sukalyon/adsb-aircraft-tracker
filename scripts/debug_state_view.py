#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.pipeline_debug import build_readsb_file_debug_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a readsb snapshot through the Phase 1 pipeline.")
    parser.add_argument(
        "--snapshot",
        required=True,
        help="Path to the readsb snapshot JSON file.",
    )
    parser.add_argument(
        "--trail-max-points",
        type=int,
        default=32,
        help="Maximum number of trail points kept per aircraft.",
    )
    parser.add_argument(
        "--stale-after-seconds",
        type=int,
        default=60,
        help="Stale track timeout used for the in-memory store.",
    )
    args = parser.parse_args()

    report = build_readsb_file_debug_report(
        ROOT / args.snapshot,
        trail_max_points=args.trail_max_points,
        stale_after_seconds=args.stale_after_seconds,
    )

    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

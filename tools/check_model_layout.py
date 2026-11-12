"""CLI check for the SMPLer-X model layout.

Usage:
  python tools/check_model_layout.py --model-dir pose_plugin/_models/smplerx --variant s32
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pose2rig_blender.worker.engines.model_layout import check_layout, format_missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--variant", default="s32", choices=["s32", "b32", "l32", "h32"])
    args = parser.parse_args()
    layout = check_layout(args.model_dir, args.variant)
    print(json.dumps(layout, ensure_ascii=False, indent=2))
    if not layout["ready"]:
        print("\n" + format_missing(layout), file=sys.stderr)
        return 1
    print("layout ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

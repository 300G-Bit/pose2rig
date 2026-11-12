"""Run one real SMPLer-X S32 inference through the Pose2Rig worker.

Usage:
  python tools/test_smplerx_infer.py --image path/to/image.jpg
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "_envs" / "smplerx" / "Scripts" / "python.exe"
SERVER = ROOT / "pose2rig_blender" / "worker" / "server.py"
MODEL_DIR = ROOT / "_models" / "smplerx"
REPO_DIR = ROOT / "_research" / "repos" / "SMPLer-X"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--variant", default="s32")
    args = parser.parse_args()
    image = str(Path(args.image).resolve())
    from PIL import Image
    with Image.open(image) as im:
        image_width, image_height = im.size
    req = {
        "type": "infer",
        "request_id": "real-s32-test",
        "engine": "smplerx",
        "image_path": image,
        "options": {
            "image_width": image_width,
            "image_height": image_height,
            "include_fingers": True,
            "model_dir": str(MODEL_DIR),
            "repo_dir": str(REPO_DIR),
            "variant": args.variant,
            "device": "cuda",
        },
    }
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.Popen(
        [str(PY), str(SERVER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, cwd=str(ROOT), env=env,
    )
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    err = proc.stderr.read()
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        print("NO_JSON", repr(line[:500]), file=sys.stderr)
        print(err[-4000:], file=sys.stderr)
        return 2
    if msg.get("type") != "result":
        print(json.dumps(msg, ensure_ascii=False, indent=2))
        print(err[-4000:], file=sys.stderr)
        return 1
    pose = msg["pose"]
    out = ROOT / "_models" / "smplerx" / "last_pose.json"
    out.write_text(json.dumps(pose, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "engine": pose["engine"]["id"],
        "joints": len(pose["source_skeleton"]["joint_names"]),
        "hands": pose["hands"]["enabled"],
        "camera": pose["camera"],
        "saved": str(out),
        "timings": pose.get("diagnostics", {}).get("timings_ms"),
    }, ensure_ascii=False, indent=2))
    print(err[-1000:], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

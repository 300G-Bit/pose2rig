"""Generate the local SMPL-X rest skeleton used by the SMPLer-X adapter.

The generated JSON is derived from the SMPL-X model (template_J). The SMPL-X
licence forbids redistribution, so the file is deliberately NOT tracked by
this repository. Run this once on a machine that has the licensed model:

    python tools/make_smplx_rest_skeleton.py --model _models/smplerx/common/utils/human_model_files/smplx/SMPLX_NEUTRAL.npz

The default output path is
pose2rig_blender/assets/skeleton/smplx_rest_skeleton.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = (
    ROOT / "_models" / "smplerx" / "common" / "utils" / "human_model_files"
    / "smplx" / "SMPLX_NEUTRAL.npz"
)
DEFAULT_OUTPUT = ROOT / "pose2rig_blender" / "assets" / "skeleton" / "smplx_rest_skeleton.json"

JOINT_NAMES = [
    "pelvis", "left_hip", "right_hip", "spine1", "left_knee", "right_knee",
    "spine2", "left_ankle", "right_ankle", "spine3", "left_foot", "right_foot",
    "neck", "left_collar", "right_collar", "head", "left_shoulder",
    "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
    "jaw", "left_eye_smplhf", "right_eye_smplhf",
    "left_index1", "left_index2", "left_index3",
    "left_middle1", "left_middle2", "left_middle3",
    "left_pinky1", "left_pinky2", "left_pinky3",
    "left_ring1", "left_ring2", "left_ring3",
    "left_thumb1", "left_thumb2", "left_thumb3",
    "right_index1", "right_index2", "right_index3",
    "right_middle1", "right_middle2", "right_middle3",
    "right_pinky1", "right_pinky2", "right_pinky3",
    "right_ring1", "right_ring2", "right_ring3",
    "right_thumb1", "right_thumb2", "right_thumb3",
]

PARENTS = [
    -1, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 9, 12, 13, 14, 16, 17, 18, 19,
    15, 15, 15, 20, 25, 26, 20, 28, 29, 20, 31, 32, 20, 34, 35, 20, 37, 38,
    21, 40, 41, 21, 43, 44, 21, 46, 47, 21, 49, 50, 21, 52, 53,
]

IDENTITY = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def build_skeleton(model_path: Path) -> dict:
    data = np.load(model_path, allow_pickle=True)
    if "J_regressor" not in data or "v_template" not in data:
        raise SystemExit(f"not a SMPL-X npz model: {model_path}")
    joints = np.asarray(data["J_regressor"], dtype=np.float64) @ np.asarray(
        data["v_template"], dtype=np.float64
    )
    if joints.shape != (len(JOINT_NAMES), 3):
        raise SystemExit(
            f"unexpected joint matrix shape {joints.shape}; expected "
            f"({len(JOINT_NAMES)}, 3)"
        )
    return {
        "schema_version": "smplx_skeleton/v1",
        "joint_names": JOINT_NAMES,
        "parents": PARENTS,
        "rest_positions": [
            [round(float(v), 6) for v in row] for row in joints
        ],
        "rest_rotations": [IDENTITY for _ in JOINT_NAMES],
        "note": (
            "Generated locally from user-provided SMPL-X neutral template_J; "
            "not distributed with the repository."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(DEFAULT_MODEL), help="SMPLX_NEUTRAL.npz path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output JSON path")
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.is_file():
        raise SystemExit(
            f"SMPL-X model not found: {model_path}\n"
            "Install the licensed SMPL-X files first (see docs/model_setup.md) "
            "or pass --model explicitly."
        )

    skeleton = build_skeleton(model_path)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {output} ({len(skeleton['joint_names'])} joints)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(r"D:\blender5.2\pose_plugin")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pose2rig_blender.core import blender_retarget
from pose2rig_blender.core.schema import validate_pose
from rig_helpers import add_mixamo_fingers, build_target_armature

SKELETON_PATH = ROOT / "pose2rig_blender" / "assets" / "skeleton" / "smplx_rest_skeleton.json"
if not SKELETON_PATH.is_file():
    print("SKELETON_MISSING: run tools/make_smplx_rest_skeleton.py; skipping hand test")
    raise SystemExit(0)
fixture = json.loads((ROOT / "pose2rig_blender" / "assets" / "fixtures" / "mock_pose.json").read_text(encoding="utf-8"))
skeleton = json.loads(SKELETON_PATH.read_text(encoding="utf-8"))

def rot_z(deg):
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]

local = [np.eye(3).tolist() for _ in skeleton["joint_names"]]
local[25] = rot_z(20)
local[26] = rot_z(30)
local[27] = rot_z(40)
pose = {
    "schema_version": "pose_result/v1",
    "request_id": "hand-test",
    "engine": {"id": "mock", "runtime": "test", "weights_sha256": None, "source_revision": "test"},
    "image": fixture["image"],
    "conventions": fixture["conventions"],
    "source_skeleton": {
        "joint_names": skeleton["joint_names"],
        "parents": skeleton["parents"],
        "rest_positions": skeleton["rest_positions"],
        "rest_rotations": skeleton["rest_rotations"],
    },
    "local_pose_rotations": local,
    "root_translation": [0, 0, 0],
    "camera": fixture["camera"],
    "hands": {"enabled": True, "confidence": None},
    "diagnostics": {"timings_ms": {}, "warnings": []},
}
pose = validate_pose(pose)
arm = build_target_armature()
add_mixamo_fingers(arm)
rest = arm.data.bones["LeftHandIndex3"].tail_local.copy()
info = blender_retarget.apply_pose(arm, pose, "MIXAMO", {"ground_snap": False})
bpy.context.view_layer.update()
posed = arm.pose.bones["LeftHandIndex3"].tail.copy()
print("HAND_INFO", info)
print("HAND_TAIL", tuple(round(v, 4) for v in rest), tuple(round(v, 4) for v in posed), "delta", round((posed-rest).length, 4))
if (posed - rest).length < 0.005:
    raise AssertionError("finger did not move")
print("HAND_TEST_OK")

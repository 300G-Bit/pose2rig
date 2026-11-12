import json
import sys
from pathlib import Path

import bpy

ROOT = Path(r"D:\blender5.2\pose_plugin")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pose2rig_blender.core import blender_retarget
from pose2rig_blender.core.schema import validate_pose
from rig_helpers import build_target_armature

pose = validate_pose(json.loads((ROOT / "pose2rig_blender" / "assets" / "fixtures" / "mock_pose.json").read_text(encoding="utf-8")))
arm = build_target_armature()
blender_retarget.apply_pose(arm, pose, "MIXAMO", {"ground_snap": True})
bpy.context.view_layer.update()
feet = ["LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase"]
zs = [arm.pose.bones[n].tail.z for n in feet]
print("FOOT_Z", [round(z, 6) for z in zs])
if abs(min(zs)) > 1e-4:
    raise AssertionError(f"ground snap failed: min z={min(zs)}")
print("GROUND_SNAP_OK")

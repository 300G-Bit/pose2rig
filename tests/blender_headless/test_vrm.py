import sys
from pathlib import Path

import bpy

ROOT = Path(r"D:\blender5.2\pose_plugin")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pose2rig_blender.core import blender_retarget
from pose2rig_blender.core.schema import validate_pose
from rig_helpers import build_target_armature, build_vrm_armature

fixture = ROOT / "pose2rig_blender" / "assets" / "fixtures" / "mock_pose.json"
import json
pose = validate_pose(json.loads(fixture.read_text(encoding="utf-8")))

arm = build_vrm_armature()
info = blender_retarget.apply_pose(arm, pose, "VRM", {"ground_snap": False})
bpy.context.view_layer.update()
print("VRM_INFO", info)
rest = arm.data.bones["J_Bip_L_Hand"].tail_local.copy()
posed = arm.pose.bones["J_Bip_L_Hand"].tail.copy()
print("VRM_HAND", tuple(round(v, 3) for v in rest), tuple(round(v, 3) for v in posed))
if (posed - rest).length < 0.05:
    raise AssertionError("VRM hand did not move")
print("VRM_RETARGET_OK")

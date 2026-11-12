import json
import sys
import tempfile
import time
from pathlib import Path

import bpy

ROOT = Path(r"D:\blender5.2\pose_plugin")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pose2rig_blender
from pose2rig_blender.ui import operators
from rig_helpers import build_target_armature

pose2rig_blender.register()
settings = bpy.context.scene.pose2rig
arm = build_target_armature()
settings.image_path = str(ROOT / "_research" / "repos" / "CameraHMR" / "demo_images" / "pexels-bertellifotografia-3856033.jpg")
settings.target_armature = arm
settings.auto_camera = False
settings.ground_snap = False

operators._start_generate(bpy.context, settings)
for _ in range(300):
    result = operators._poll_generate()
    if result is None:
        break
    time.sleep(0.03)
posed_tail = arm.pose.bones["LeftHand"].tail.copy()
if not settings.last_pose_json:
    raise AssertionError("no pose generated")

out = Path(tempfile.gettempdir()) / "pose2rig_test_pose.json"
bpy.ops.pose2rig.save_pose(filepath=str(out))
print("SAVED", out, out.stat().st_size)
if not out.is_file():
    raise AssertionError("save_pose did not write file")

bpy.ops.pose2rig.reset()
bpy.context.view_layer.update()
rest_tail = arm.pose.bones["LeftHand"].tail.copy()
if (rest_tail - posed_tail).length < 0.05:
    raise AssertionError("reset did not clear the pose")

bpy.ops.pose2rig.load_pose(filepath=str(out))
bpy.context.view_layer.update()
loaded_tail = arm.pose.bones["LeftHand"].tail.copy()
print("LOADED", tuple(round(v, 4) for v in loaded_tail), "delta", (loaded_tail - posed_tail).length)
if (loaded_tail - posed_tail).length > 1e-4:
    raise AssertionError("load_pose did not restore the saved pose")

pose2rig_blender.unregister()
print("SAVE_LOAD_TEST_OK")

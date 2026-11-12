import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(r"D:\blender5.2\pose_plugin")
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pose2rig_blender
from pose2rig_blender.ui import operators
from rig_helpers import build_target_armature

print("REGISTER_START")
pose2rig_blender.register()
print("REGISTER_OK")
settings = bpy.context.scene.pose2rig
print("SETTINGS_OK", settings.engine, settings.preset, settings.status)
print("OPERATOR", hasattr(bpy.ops.pose2rig, "generate"))
print("PANEL", hasattr(bpy.types, "VIEW3D_PT_pose2rig"))

# Smoke: start a mock generation and poll manually (background mode has no UI timer loop).
settings.image_path = str(ROOT / "_research" / "repos" / "CameraHMR" / "demo_images" / "pexels-bertellifotografia-3856033.jpg")
settings.target_armature = build_target_armature()
settings.status = "test"
operators._start_generate(bpy.context, settings)
print("START_STATUS", settings.status)
import time
for _ in range(200):
    result = operators._poll_generate()
    if result is None:
        break
    time.sleep(0.05)
print("FINAL_STATUS", settings.status)
print("HAS_POSE", bool(settings.last_pose_json))
pose2rig_blender.unregister()
print("UNREGISTER_OK")

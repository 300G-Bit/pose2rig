import sys, time
from pathlib import Path
import bpy
import addon_utils
sys.path.insert(0, str(Path(r"D:\blender5.2\pose_plugin") / "tests" / "blender_headless"))
from rig_helpers import build_target_armature
addon_utils.enable("bl_ext.user_default.pose2rig", default_set=True)
import bl_ext.user_default.pose2rig.ui.operators as ops
settings = bpy.context.scene.pose2rig
settings.image_path = r"D:\blender5.2\pose_plugin\_research\repos\CameraHMR\demo_images\pexels-bertellifotografia-3856033.jpg"
settings.target_armature = build_target_armature()
settings.auto_camera = False
settings.ground_snap = False
ops._start_generate(bpy.context, settings)
for _ in range(400):
    if ops._poll_generate() is None:
        break
    time.sleep(0.03)
print("INSTALLED_STATUS", settings.status)
print("INSTALLED_HAS_POSE", bool(settings.last_pose_json))
if not settings.last_pose_json:
    raise SystemExit(1)

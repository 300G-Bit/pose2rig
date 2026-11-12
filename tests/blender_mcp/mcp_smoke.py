"""Paste this into Blender 5.2.2 via Blender MCP (blender_rt_do) or run manually.

It assumes the Pose2Rig extension is installed and enabled, and the reference
image exists.  It creates a synthetic target armature, runs the mock engine,
and prints a compact JSON status for the MCP session.
"""

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(r"D:\blender5.2\pose_plugin")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "blender_headless"))

from rig_helpers import build_target_armature


def main():
    print(json.dumps({
        "blender": list(bpy.app.version),
        "addon": "bl_ext.user_default.pose2rig" in bpy.context.preferences.addons,
        "panel": hasattr(bpy.types, "VIEW3D_PT_pose2rig"),
        "scene_prop": hasattr(bpy.types.Scene, "pose2rig"),
    }, ensure_ascii=False))
    if not hasattr(bpy.types.Scene, "pose2rig"):
        raise RuntimeError("Pose2Rig extension is not enabled")
    settings = bpy.context.scene.pose2rig
    settings.image_path = str(ROOT / "_research" / "repos" / "CameraHMR" / "demo_images" / "pexels-bertellifotografia-3856033.jpg")
    settings.target_armature = build_target_armature()
    settings.auto_camera = True
    settings.ground_snap = True
    settings.engine = "mock"
    bpy.ops.pose2rig.generate()
    print(json.dumps({"status": settings.status, "has_pose": bool(settings.last_pose_json)}, ensure_ascii=False))


main()

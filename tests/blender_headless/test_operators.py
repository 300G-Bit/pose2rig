import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion

ROOT = Path(r"D:\blender5.2\pose_plugin")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pose2rig_blender
from pose2rig_blender.ui import operators
from rig_helpers import build_target_armature


def wait_generate(settings):
    operators._start_generate(bpy.context, settings)
    for _ in range(400):
        result = operators._poll_generate()
        if result is None:
            return
        time.sleep(0.03)
    raise AssertionError("generate timed out")


pose2rig_blender.register()
settings = bpy.context.scene.pose2rig
arm = build_target_armature()
settings.image_path = str(ROOT / "_research" / "repos" / "CameraHMR" / "demo_images" / "pexels-bertellifotografia-3856033.jpg")
settings.target_armature = arm
settings.ground_snap = False
settings.auto_camera = False

rest_tail = arm.pose.bones["LeftHand"].tail.copy()
wait_generate(settings)
print("GEN", settings.status)
tail0 = arm.pose.bones["LeftHand"].tail.copy()
if (tail0 - rest_tail).length < 0.05:
    raise AssertionError("generate did not move the hand")

# The mock fixture has an identity collar; verify the slider math directly.
from pose2rig_blender.core.pose_modifiers import _scale_delta
collar = arm.pose.bones["LeftShoulder"]
collar.rotation_mode = "QUATERNION"
collar.rotation_quaternion = Quaternion((0.0, 1.0, 0.0), math.radians(30.0))
_scale_delta(collar, 0.5)
bpy.context.view_layer.update()
print("SCALE_DELTA", round(math.degrees(collar.rotation_quaternion.angle), 3))
if abs(math.degrees(collar.rotation_quaternion.angle) - 15.0) > 1e-3:
    raise AssertionError("shoulder_relax math is wrong")
# Reapply the generated pose before continuing.
wait_generate(settings)

# Apply clears the snapshot.
bpy.ops.pose2rig.apply()
print("APPLY", settings.status)

# Generate again, then cancel must restore the pose that existed before this generate.
before = arm.pose.bones["LeftHand"].tail.copy()
wait_generate(settings)
bpy.ops.pose2rig.cancel()
bpy.context.view_layer.update()
tail3 = arm.pose.bones["LeftHand"].tail.copy()
print("CANCEL", tuple(round(v, 3) for v in tail3), "diff", (tail3 - before).length)
if (tail3 - before).length > 1e-4:
    raise AssertionError("cancel did not restore the pre-generate pose")

# Euler-mode snapshot/restore must preserve matrix_basis.
euler_bone = arm.pose.bones["LeftShoulder"]
euler_bone.rotation_mode = "XYZ"
euler_bone.rotation_euler = (0.2, 0.3, 0.4)
bpy.context.view_layer.update()
euler_before = euler_bone.matrix_basis.copy()
euler_snap = operators.snapshot_pose(arm)
euler_bone.rotation_mode = "QUATERNION"
euler_bone.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), 0.5)
operators.restore_pose(arm, euler_snap)
euler_diff = max(abs(euler_before[r][c] - euler_bone.matrix_basis[r][c]) for r in range(4) for c in range(4))
print("EULER_RESTORE", round(euler_diff, 9))
if euler_diff > 1e-6:
    raise AssertionError("Euler pose restore failed")

bpy.ops.pose2rig.reset()
bpy.context.view_layer.update()
tail4 = arm.pose.bones["LeftHand"].tail.copy()
print("RESET", settings.status, "diff", (tail4 - rest_tail).length)
if (tail4 - rest_tail).length > 1e-4:
    raise AssertionError("reset did not restore rest")
pose2rig_blender.unregister()
print("OPERATOR_TESTS_PASSED")

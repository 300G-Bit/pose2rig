import json
import math
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pose2rig_blender.core import blender_retarget, camera_builder
from pose2rig_blender.core.schema import validate_pose


def load_fixture():
    path = ROOT / "pose2rig_blender" / "assets" / "fixtures" / "mock_pose.json"
    return validate_pose(json.loads(path.read_text(encoding="utf-8")))


def build_target_armature():
    data = bpy.data.armatures.new("TargetRig")
    obj = bpy.data.objects.new("TargetRig", data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    # name: (head, tail, parent)
    spec = {
        "Hips": ((0, 0.95, 0), (0, 1.03, 0), None),
        "Spine": ((0, 1.03, 0), (0, 1.15, 0), "Hips"),
        "Spine1": ((0, 1.15, 0), (0, 1.27, 0), "Spine"),
        "Spine2": ((0, 1.27, 0), (0, 1.43, 0), "Spine1"),
        "Neck": ((0, 1.43, 0), (0, 1.52, 0), "Spine2"),
        "Head": ((0, 1.52, 0), (0, 1.68, 0), "Neck"),
        "LeftShoulder": ((0.05, 1.40, 0), (0.19, 1.40, 0), "Spine2"),
        "LeftArm": ((0.19, 1.40, 0), (0.45, 1.40, 0), "LeftShoulder"),
        "LeftForeArm": ((0.45, 1.40, 0), (0.70, 1.40, 0), "LeftArm"),
        "LeftHand": ((0.70, 1.40, 0), (0.82, 1.40, 0), "LeftForeArm"),
        "RightShoulder": ((-0.05, 1.40, 0), (-0.19, 1.40, 0), "Spine2"),
        "RightArm": ((-0.19, 1.40, 0), (-0.45, 1.40, 0), "RightShoulder"),
        "RightForeArm": ((-0.45, 1.40, 0), (-0.70, 1.40, 0), "RightArm"),
        "RightHand": ((-0.70, 1.40, 0), (-0.82, 1.40, 0), "RightForeArm"),
        "LeftUpLeg": ((0.09, 0.92, 0), (0.10, 0.52, 0), "Hips"),
        "LeftLeg": ((0.10, 0.52, 0), (0.10, 0.10, 0), "LeftUpLeg"),
        "LeftFoot": ((0.10, 0.10, 0), (0.10, 0.03, 0.07), "LeftLeg"),
        "LeftToeBase": ((0.10, 0.03, 0.07), (0.10, 0.03, 0.15), "LeftFoot"),
        "RightUpLeg": ((-0.09, 0.92, 0), (-0.10, 0.52, 0), "Hips"),
        "RightLeg": ((-0.10, 0.52, 0), (-0.10, 0.10, 0), "RightUpLeg"),
        "RightFoot": ((-0.10, 0.10, 0), (-0.10, 0.03, 0.07), "RightLeg"),
        "RightToeBase": ((-0.10, 0.03, 0.07), (-0.10, 0.03, 0.15), "RightFoot"),
    }
    created = {}
    for name, (head, tail, parent) in spec.items():
        bone = data.edit_bones.new(name)
        bone.head = head
        bone.tail = tail
        bone.roll = 0.0
        created[name] = bone
    for name, (_head, _tail, parent) in spec.items():
        if parent:
            created[name].parent = created[parent]
    bpy.ops.object.mode_set(mode="POSE")
    return obj


def assert_close(a, b, tol=1e-5, label=""):
    if abs(a - b) > tol:
        raise AssertionError(f"{label}: {a} != {b}")


def test_camera():
    pose = load_fixture()
    scene = bpy.context.scene
    cam = camera_builder.create_or_update_camera(scene, pose, image_path=None, opacity=0.5)
    # 1200x1600 portrait, fx=2000, sensor=36 -> 45 mm under AUTO
    assert_close(cam.data.lens, 45.0, 1e-4, "lens_mm")
    center = camera_builder.project_point(scene, cam, (0, 0, 0))
    assert_close(center.x, 0.5, 1e-4, "center.x")
    assert_close(center.y, 0.5, 1e-4, "center.y")
    left = camera_builder.project_point(scene, cam, (-0.5, 0, 0))
    right = camera_builder.project_point(scene, cam, (0.5, 0, 0))
    if not (left.x < 0.5 < right.x):
        raise AssertionError("projection x direction is wrong")
    if (cam.location - Vector((0, -3.2, 0))).length > 1e-5:
        raise AssertionError(f"camera location wrong: {tuple(cam.location)}")
    # Fit modes: fx=fy=2000 on 1200x1600 with 36mm sensor.
    assert_close(camera_builder._lens_mm(2000, 2000, 1200, 1600, 36, "AUTO"), 45.0, 1e-5, "auto")
    assert_close(camera_builder._lens_mm(2000, 2000, 1200, 1600, 36, "HORIZONTAL"), 60.0, 1e-5, "horizontal")
    assert_close(camera_builder._lens_mm(2000, 2000, 1200, 1600, 36, "VERTICAL"), 45.0, 1e-5, "vertical")
    # Principal point offset: cx=700, cy=900 on 1200x1600.
    pose_shift = load_fixture()
    pose_shift["camera"]["cx_px"] = 700.0
    pose_shift["camera"]["cy_px"] = 900.0
    cam2 = camera_builder.create_or_update_camera(scene, pose_shift, image_path=None, opacity=0.5, name="Pose2Rig_Camera_Shift")
    shifted = camera_builder.project_point(scene, cam2, (0, 0, 0))
    assert_close(shifted.x, 700.0 / 1200.0, 1e-4, "principal x")
    assert_close(shifted.y, 1.0 - 900.0 / 1600.0, 1e-4, "principal y")
    print("TEST_CAMERA_OK", cam.data.lens, center.x, center.y, tuple(round(v, 3) for v in cam.location), "shift", round(shifted.x, 4), round(shifted.y, 4))


def test_retarget():
    pose = load_fixture()
    arm = build_target_armature()
    rest_tail = arm.data.bones["LeftHand"].tail_local.copy()
    info = blender_retarget.apply_pose(arm, pose, "MIXAMO", {"ground_snap": False})
    bpy.context.view_layer.update()
    pb = arm.pose.bones["LeftHand"]
    if (pb.tail - rest_tail).length < 0.05:
        raise AssertionError(f"LeftHand did not move: rest={tuple(rest_tail)} pose={tuple(pb.tail)}")
    print("TEST_RETARGET_OK", info, "rest", tuple(round(v, 3) for v in rest_tail), "pose", tuple(round(v, 3) for v in pb.tail))
    blender_retarget.clear_pose(arm)
    bpy.context.view_layer.update()
    reset_tail = arm.pose.bones["LeftHand"].tail
    if (reset_tail - rest_tail).length > 1e-5:
        raise AssertionError("clear_pose did not restore rest")
    print("TEST_CLEAR_OK")


def main():
    try:
        test_camera()
        test_retarget()
    except Exception:
        traceback.print_exc()
        raise
    print("ALL_CORE_TESTS_PASSED")


main()

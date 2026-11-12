"""Non-destructive pose adjustments for Pose2Rig."""

from __future__ import annotations

import bpy
from mathutils import Quaternion, Vector


def _bone_name_for_source(armature, preset, source_joint):
    names = {b.name for b in armature.data.bones}
    for candidate in preset.get("bone_mapping", {}).get(source_joint, []):
        for prefix in preset.get("prefixes", [""]):
            if prefix + candidate in names:
                return prefix + candidate
    return None


def _scale_delta(pb, factor: float):
    """Scale the local pose rotation around its own axis.

    ``pb.rotation_quaternion`` is already the matrix_basis rotation relative
    to the bone rest pose; it must not be multiplied by the rest quaternion
    again.
    """
    if pb is None:
        return
    pb.rotation_mode = "QUATERNION"
    q_pose = pb.rotation_quaternion.copy()
    if q_pose.angle < 1e-8:
        return
    pb.rotation_quaternion = Quaternion(q_pose.axis, q_pose.angle * float(factor))


def apply_shoulder_relax(armature, info, factor: float):
    factor = max(0.0, min(1.0, float(factor)))
    for joint in ("left_collar", "right_collar"):
        name = _bone_name_for_source(armature, info["preset"], joint)
        if name:
            _scale_delta(armature.pose.bones.get(name), 1.0 - 0.6 * factor)
    bpy.context.view_layer.update()


def apply_spine_influence(armature, info, factor: float):
    factor = float(factor)
    for joint in ("spine1", "spine2", "spine3"):
        name = _bone_name_for_source(armature, info["preset"], joint)
        if name:
            _scale_delta(armature.pose.bones.get(name), factor)
    bpy.context.view_layer.update()


def snap_to_ground(armature, info):
    """Move the root so the lowest foot tail sits at world Z=0."""
    foot_names = []
    for joint in ("left_ankle", "right_ankle", "left_foot", "right_foot"):
        name = _bone_name_for_source(armature, info["preset"], joint)
        if name and name not in foot_names:
            foot_names.append(name)
    if not foot_names:
        return
    bpy.context.view_layer.update()
    z_min = min(
        (armature.matrix_world @ armature.pose.bones[name].tail).z
        for name in foot_names if name in armature.pose.bones
    )
    if abs(z_min) < 1e-9:
        return
    root_name = info["preset"].get("root")
    root_pb = armature.pose.bones.get(root_name) if root_name else None
    if root_pb is None:
        for pb in armature.pose.bones:
            if pb.parent is None:
                root_pb = pb
                break
    if root_pb is None:
        return
    object_rotation = armature.matrix_world.to_quaternion().to_matrix()
    delta_arm = object_rotation.inverted() @ Vector((0.0, 0.0, -z_min))
    root_pb.location = root_pb.location + (root_pb.bone.matrix_local.to_3x3().inverted() @ delta_arm)
    bpy.context.view_layer.update()

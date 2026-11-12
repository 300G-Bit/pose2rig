"""Shared synthetic armatures for Blender headless tests."""

from __future__ import annotations

import bpy
from mathutils import Vector


def build_target_armature(name="TargetRig"):
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

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
    for bone_name, (head, tail, parent) in spec.items():
        bone = data.edit_bones.new(bone_name)
        bone.head = head
        bone.tail = tail
        bone.roll = 0.0
        created[bone_name] = bone
    for bone_name, (_head, _tail, parent) in spec.items():
        if parent:
            created[bone_name].parent = created[parent]
    bpy.ops.object.mode_set(mode="POSE")
    return obj


def build_vrm_armature(name="VRMTarget"):
    """Minimal VRM-humanoid-named armature using the same proportions."""
    data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    spec = {
        "J_Bip_C_Hips": ((0, 0.95, 0), (0, 1.03, 0), None),
        "J_Bip_C_Spine": ((0, 1.03, 0), (0, 1.15, 0), "J_Bip_C_Hips"),
        "J_Bip_C_Chest": ((0, 1.15, 0), (0, 1.27, 0), "J_Bip_C_Spine"),
        "J_Bip_C_UpperChest": ((0, 1.27, 0), (0, 1.43, 0), "J_Bip_C_Chest"),
        "J_Bip_C_Neck": ((0, 1.43, 0), (0, 1.52, 0), "J_Bip_C_UpperChest"),
        "J_Bip_C_Head": ((0, 1.52, 0), (0, 1.68, 0), "J_Bip_C_Neck"),
        "J_Bip_L_Shoulder": ((0.05, 1.40, 0), (0.19, 1.40, 0), "J_Bip_C_UpperChest"),
        "J_Bip_L_UpperArm": ((0.19, 1.40, 0), (0.45, 1.40, 0), "J_Bip_L_Shoulder"),
        "J_Bip_L_LowerArm": ((0.45, 1.40, 0), (0.70, 1.40, 0), "J_Bip_L_UpperArm"),
        "J_Bip_L_Hand": ((0.70, 1.40, 0), (0.82, 1.40, 0), "J_Bip_L_LowerArm"),
        "J_Bip_R_Shoulder": ((-0.05, 1.40, 0), (-0.19, 1.40, 0), "J_Bip_C_UpperChest"),
        "J_Bip_R_UpperArm": ((-0.19, 1.40, 0), (-0.45, 1.40, 0), "J_Bip_R_Shoulder"),
        "J_Bip_R_LowerArm": ((-0.45, 1.40, 0), (-0.70, 1.40, 0), "J_Bip_R_UpperArm"),
        "J_Bip_R_Hand": ((-0.70, 1.40, 0), (-0.82, 1.40, 0), "J_Bip_R_LowerArm"),
        "J_Bip_L_UpperLeg": ((0.09, 0.92, 0), (0.10, 0.52, 0), "J_Bip_C_Hips"),
        "J_Bip_L_LowerLeg": ((0.10, 0.52, 0), (0.10, 0.10, 0), "J_Bip_L_UpperLeg"),
        "J_Bip_L_Foot": ((0.10, 0.10, 0), (0.10, 0.03, 0.07), "J_Bip_L_LowerLeg"),
        "J_Bip_L_ToeBase": ((0.10, 0.03, 0.07), (0.10, 0.03, 0.15), "J_Bip_L_Foot"),
        "J_Bip_R_UpperLeg": ((-0.09, 0.92, 0), (-0.10, 0.52, 0), "J_Bip_C_Hips"),
        "J_Bip_R_LowerLeg": ((-0.10, 0.52, 0), (-0.10, 0.10, 0), "J_Bip_R_UpperLeg"),
        "J_Bip_R_Foot": ((-0.10, 0.10, 0), (-0.10, 0.03, 0.07), "J_Bip_R_LowerLeg"),
        "J_Bip_R_ToeBase": ((-0.10, 0.03, 0.07), (-0.10, 0.03, 0.15), "J_Bip_R_Foot"),
    }
    created = {}
    for bone_name, (head, tail, parent) in spec.items():
        bone = data.edit_bones.new(bone_name)
        bone.head = head
        bone.tail = tail
        bone.roll = 0.0
        created[bone_name] = bone
    for bone_name, (_head, _tail, parent) in spec.items():
        if parent:
            created[bone_name].parent = created[parent]
    bpy.ops.object.mode_set(mode="POSE")
    return obj


def add_mixamo_fingers(arm):
    """Add 30 simple finger bones under LeftHand/RightHand."""
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit = arm.data.edit_bones
    fingers = [("Thumb", 3), ("Index", 3), ("Middle", 3), ("Ring", 3), ("Pinky", 3)]
    for side, sign in (("Left", 1.0), ("Right", -1.0)):
        hand = edit.get(f"{side}Hand")
        if hand is None:
            continue
        base = hand.tail.copy()
        # Spread fingers across local Y, extend along the hand direction.
        for f_index, (finger, segments) in enumerate(fingers):
            parent = hand
            start = base + Vector((0, 0.01 * (f_index - 2), 0.0))
            for seg in range(1, segments + 1):
                name = f"{side}Hand{finger}{seg}"
                bone = edit.new(name)
                bone.head = start
                bone.tail = start + Vector((0.03 * sign, 0.0, 0.0))
                bone.parent = parent
                bone.use_connect = False
                parent = bone
                start = bone.tail.copy()
    bpy.ops.object.mode_set(mode="POSE")
    return arm

"""Scene properties for Pose2Rig."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup


def _update_pose_options(self, context):
    from . import operators
    operators.reapply_last_pose(context, self)


def _poll_armature(self, obj):
    return obj.type == "ARMATURE"


class Pose2RigSettings(PropertyGroup):
    image_path: StringProperty(
        name="Reference Image",
        description="PNG/JPEG/WebP reference image",
        subtype="FILE_PATH",
    )
    target_armature: PointerProperty(
        name="Target Rig",
        description="Armature that receives the pose",
        type=bpy.types.Object,
        poll=_poll_armature,
    )
    preset: EnumProperty(
        name="Preset",
        items=[
            ("AUTO", "Auto Detect", "Detect Mixamo/VRM/MMD from bone names"),
            ("MIXAMO", "Mixamo", "Mixamo humanoid bone names"),
            ("VRM", "VRM Humanoid", "VRM/VRM Add-on humanoid bone names"),
            ("MMD", "MMD (PMX)", "MMD standard Japanese bone names"),
        ],
        default="AUTO",
    )
    mapping_mode: EnumProperty(
        name="Mapping Mode",
        items=[
            ("AUTO", "Auto", "Use input-quality detection to choose full or upper body"),
            ("FULL", "Full Body", "Always map all 55 joints"),
            ("UPPER_BODY", "Upper Body", "Map upper body only; leave legs at rest"),
        ],
        default="AUTO",
    )
    engine: EnumProperty(
        name="Engine",
        items=[
            ("mock", "Mock (test)", "Deterministic fixture, no model needed"),
            ("smplerx", "SMPLer-X", "SMPLer-X S32/B32 adapter"),
        ],
        default="mock",
    )
    include_fingers: BoolProperty(
        name="Include Fingers",
        description="Map 30 hand joints when the target rig has them",
        default=True,
    )
    auto_camera: BoolProperty(
        name="Auto Match Camera",
        description="Create a camera matching the predicted intrinsics",
        default=True,
    )
    show_reference: BoolProperty(
        name="Show Reference Background",
        description="Load the reference image as camera background",
        default=True,
    )
    opacity: FloatProperty(
        name="Reference Opacity",
        min=0.0, max=1.0, default=0.5,
    )
    shoulder_relax: FloatProperty(
        name="Shoulder Relax",
        min=0.0, max=1.0, default=0.0,
        update=_update_pose_options,
    )
    spine_influence: FloatProperty(
        name="Spine Influence",
        min=0.5, max=1.5, default=1.0,
        update=_update_pose_options,
    )
    ground_snap: BoolProperty(
        name="Snap Feet to Ground",
        default=True,
        update=_update_pose_options,
    )
    status: StringProperty(
        name="Status",
        default="Idle",
    )
    last_warnings: StringProperty(
        name="Warnings",
        default="",
        options={"HIDDEN"},
    )
    progress: FloatProperty(
        name="Progress",
        min=0.0, max=1.0, default=0.0,
    )
    last_pose_json: StringProperty(
        name="Last Pose",
        default="",
        options={"HIDDEN"},
    )
    last_result_path: StringProperty(
        name="Last Result",
        default="",
        subtype="FILE_PATH",
        options={"HIDDEN"},
    )

"""N-panel UI for Pose2Rig."""

from __future__ import annotations

import bpy
from bpy.types import Panel


class VIEW3D_PT_pose2rig(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pose2Rig"
    bl_label = "Pose2Rig"

    def draw(self, context):
        layout = self.layout
        settings = getattr(context.scene, "pose2rig", None)
        if settings is None:
            layout.label(text="Pose2Rig is not initialized", icon="ERROR")
            return

        box = layout.box()
        box.label(text="1. Reference Image", icon="IMAGE_DATA")
        box.prop(settings, "image_path", text="")
        box.prop(settings, "auto_camera")
        if settings.auto_camera:
            row = box.row(align=True)
            row.prop(settings, "show_reference")
            row.prop(settings, "opacity", text="Opacity")

        box = layout.box()
        box.label(text="2. Target Character Rig", icon="ARMATURE_DATA")
        box.prop(settings, "target_armature", text="")
        box.prop(settings, "preset")
        box.prop(settings, "mapping_mode")
        box.prop(settings, "engine")
        box.prop(settings, "include_fingers")
        if settings.engine == "smplerx":
            box.operator("pose2rig.probe_engine", icon="CHECKMARK")

        box = layout.box()
        box.label(text="3. Generate & Pose Polish", icon="POSE_DATA")
        row = box.row()
        row.scale_y = 1.4
        row.operator("pose2rig.generate", icon="PLAY")
        if settings.status:
            box.label(text=settings.status, icon="INFO")
        if settings.progress > 0.0 and settings.progress < 1.0:
            box.label(text=f"Progress: {int(settings.progress * 100)}%")
        if settings.last_warnings:
            box.label(text=settings.last_warnings, icon="ERROR")

        col = box.column(align=True)
        col.prop(settings, "shoulder_relax")
        col.prop(settings, "spine_influence")
        col.prop(settings, "ground_snap")

        row = box.row(align=True)
        row.operator("pose2rig.apply", icon="CHECKMARK")
        row.operator("pose2rig.cancel", icon="CANCEL")
        row.operator("pose2rig.reset", icon="LOOP_BACK")

        row = box.row(align=True)
        row.operator("pose2rig.save_pose", icon="FILE_TICK")
        row.operator("pose2rig.load_pose", icon="FILEBROWSER")


CLASSES = [VIEW3D_PT_pose2rig]

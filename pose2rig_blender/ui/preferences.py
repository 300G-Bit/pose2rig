"""Add-on preferences for Pose2Rig."""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences


class Pose2RigPreferences(AddonPreferences):
    bl_idname = __package__.rsplit(".", 1)[0]

    worker_python: StringProperty(
        name="Worker Python",
        description="Python interpreter used to launch the pose worker. Leave empty to use Blender's Python (mock engine only)",
        subtype="FILE_PATH",
        default="",
    )
    worker_script: StringProperty(
        name="Worker Script",
        description="Path to worker/server.py. Leave empty to use the bundled worker",
        subtype="FILE_PATH",
        default="",
    )
    model_dir: StringProperty(
        name="SMPLer-X Model Directory",
        description="Directory containing SMPLer-X checkpoints and SMPL-X model files",
        subtype="DIR_PATH",
        default="",
    )
    repo_dir: StringProperty(
        name="SMPLer-X Repo",
        description="Path to the SMPLer-X source checkout (contains main/inference.py)",
        subtype="DIR_PATH",
        default="",
    )
    worker_timeout: IntProperty(
        name="Worker Timeout (seconds)",
        description="Maximum time to wait for one inference",
        default=600, min=30, max=3600,
    )
    variant: EnumProperty(
        name="SMPLer-X Variant",
        items=[
            ("s32", "S32 (32M)", "Lightest, lowest quality"),
            ("b32", "B32 (103M)", "Balanced"),
            ("l32", "L32 (327M)", "Heavier"),
        ],
        default="s32",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Worker runtime")
        layout.prop(self, "worker_python")
        layout.prop(self, "worker_script")
        layout.prop(self, "model_dir")
        layout.prop(self, "repo_dir")
        layout.prop(self, "variant")
        layout.prop(self, "worker_timeout")
        layout.label(text="Mock engine uses Blender's Python; SMPLer-X needs its own environment.", icon="INFO")


CLASSES = [Pose2RigPreferences]

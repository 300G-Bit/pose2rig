"""Pose2Rig Blender extension entry point.

The module is import-safe outside Blender: the worker process imports
pose2rig_blender.core.schema without needing bpy.
"""

from __future__ import annotations

try:
    import bpy  # type: ignore
    from bpy.props import PointerProperty  # type: ignore
    _HAS_BPY = True
except ModuleNotFoundError:  # worker process / unit tests
    bpy = None  # type: ignore
    PointerProperty = None  # type: ignore
    _HAS_BPY = False

bl_info = {
    "name": "Pose2Rig",
    "author": "Pose2Rig PoC",
    "version": (0, 2, 2),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Pose2Rig",
    "description": "Single image to 3D pose",
    "category": "Animation",
}

if _HAS_BPY:
    from .ui.preferences import Pose2RigPreferences
    from .ui.properties import Pose2RigSettings
    from .ui.operators import CLASSES as OPERATOR_CLASSES
    from .ui.panels import CLASSES as PANEL_CLASSES
    _CLASSES = [Pose2RigPreferences, Pose2RigSettings] + list(OPERATOR_CLASSES) + list(PANEL_CLASSES)
else:
    _CLASSES = []


def register():
    if not _HAS_BPY:
        return
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pose2rig = PointerProperty(type=Pose2RigSettings)


def unregister():
    if not _HAS_BPY:
        return
    if hasattr(bpy.types.Scene, "pose2rig"):
        del bpy.types.Scene.pose2rig
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

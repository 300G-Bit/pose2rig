"""Pose snapshot/restore for preview and undo."""

from __future__ import annotations

import bpy
from mathutils import Matrix


def snapshot_pose(armature):
    """Snapshot every pose channel through matrix_basis.

    matrix_basis contains location/rotation/scale independent of the current
    rotation_mode, so Euler and axis-angle bones restore correctly too.
    """
    snap = {}
    for pb in armature.pose.bones:
        snap[pb.name] = {
            "rotation_mode": pb.rotation_mode,
            "matrix_basis": tuple(tuple(float(v) for v in row) for row in pb.matrix_basis),
            "constraints": [(c.name, c.type, bool(c.mute)) for c in pb.constraints],
        }
    return snap


def restore_pose(armature, snap):
    if not snap:
        return
    for pb in armature.pose.bones:
        data = snap.get(pb.name)
        if not data:
            continue
        pb.rotation_mode = data["rotation_mode"]
        pb.matrix_basis = Matrix(data["matrix_basis"])
        for name, _type, mute in data.get("constraints", []):
            constraint = pb.constraints.get(name)
            if constraint is not None:
                constraint.mute = mute
    bpy.context.view_layer.update()

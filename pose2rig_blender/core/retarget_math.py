"""Pure 3x3 retarget math shared by Blender and unit tests.

All matrices are numpy float64 arrays in row-major form.  A rotation matrix
maps column vectors: v_world = R @ v_local.  No bpy imports are allowed here.
"""

from __future__ import annotations

import numpy as np


class RetargetMathError(ValueError):
    """Raised when a matrix or skeleton graph is not usable."""


def as_mat3(value, name="matrix"):
    """Validate and return a 3x3 float64 rotation matrix."""
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape != (3, 3):
        raise RetargetMathError(f"{name}: expected (3,3), got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise RetargetMathError(f"{name}: contains NaN/Inf")
    return arr


def orthonormalize(matrix):
    """Return the nearest proper rotation matrix (det = +1)."""
    m = as_mat3(matrix)
    u, _s, vt = np.linalg.svd(m)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u = u.copy()
        u[:, -1] *= -1.0
        r = u @ vt
    return r


def validate_rotation(matrix, name="matrix", atol=1e-3):
    """Raise if matrix is not a proper rotation within tolerance."""
    m = as_mat3(matrix, name)
    if not np.allclose(m.T @ m, np.eye(3), atol=atol):
        raise RetargetMathError(f"{name}: not orthonormal")
    if np.linalg.det(m) < 0.0:
        raise RetargetMathError(f"{name}: determinant is negative")
    return m


def validate_skeleton(joint_names, parents):
    """Validate a parent table: root is -1, every parent points earlier."""
    if len(joint_names) != len(parents):
        raise RetargetMathError("joint_names and parents have different lengths")
    if not parents:
        raise RetargetMathError("empty skeleton")
    for i, p in enumerate(parents):
        if not isinstance(p, (int, np.integer)):
            raise RetargetMathError(f"parent[{i}] is not an int")
        if p < -1:
            raise RetargetMathError(f"parent[{i}] < -1")
        if p >= i:
            raise RetargetMathError(f"parent[{i}] must point to an earlier joint")
    return list(range(len(joint_names)))


def rest_relative(rest_rotations, parents):
    """Convert armature-space rest rotations into parent-relative rotations."""
    rest = [validate_rotation(m, f"rest[{i}]") for i, m in enumerate(rest_rotations)]
    if len(rest) != len(parents):
        raise RetargetMathError("rest_rotations/parents length mismatch")
    rel = []
    for i, p in enumerate(parents):
        if p < 0:
            rel.append(rest[i].copy())
        else:
            rel.append(orthonormalize(rest[p].T @ rest[i]))
    return rel


def source_world(rest_rotations, parents, local_pose_rotations):
    """Compute source joint world rotations from local pose rotations."""
    rel = rest_relative(rest_rotations, parents)
    if len(local_pose_rotations) != len(parents):
        raise RetargetMathError("local_pose_rotations length mismatch")
    world = []
    for i, p in enumerate(parents):
        local = validate_rotation(local_pose_rotations[i], f"local_pose[{i}]")
        base = world[p] if p >= 0 else np.eye(3)
        world.append(orthonormalize(base @ rel[i] @ local))
    return world


def world_deltas(pose_world, rest_world):
    """D_j = S_pose_j @ S_rest_j^-1 (world-space rotation increment)."""
    if len(pose_world) != len(rest_world):
        raise RetargetMathError("pose/rest length mismatch")
    return [
        orthonormalize(validate_rotation(pose_world[i], f"pose[{i}]") @
                       validate_rotation(rest_world[i], f"rest[{i}]").T)
        for i in range(len(pose_world))
    ]


def target_world(deltas, source_map, target_rest, target_parents, alignments=None):
    """Compute target bone world rotations.

    source_map maps target bone index -> source joint index.  Unmapped bones
    simply follow their parent's rest-relative rotation.  ``alignments`` maps
    target bone index -> A_b (target rest direction -> source rest direction),
    applied before the source world delta.
    """
    rel = rest_relative(target_rest, target_parents)
    alignments = alignments or {}
    world = []
    for i, p in enumerate(target_parents):
        base = world[p] if p >= 0 else np.eye(3)
        if i in source_map:
            src = source_map[i]
            if src < 0 or src >= len(deltas):
                raise RetargetMathError(f"source_map[{i}] out of range")
            align = alignments.get(i, np.eye(3))
            world.append(orthonormalize(deltas[src] @ align @ target_rest[i]))
        else:
            world.append(orthonormalize(base @ rel[i]))
    return world, rel


def local_basis(target_world_rotations, rel, parents):
    """Convert target world rotations to local pose basis matrices."""
    out = []
    for i, p in enumerate(parents):
        base = target_world_rotations[p] if p >= 0 else np.eye(3)
        out.append(orthonormalize((base @ rel[i]).T @ target_world_rotations[i]))
    return out


def rotation_between(a, b):
    """Return the minimal rotation matrix mapping unit-ish vector a to b."""
    va = np.asarray(a, dtype=np.float64).reshape(3)
    vb = np.asarray(b, dtype=np.float64).reshape(3)
    na = np.linalg.norm(va); nb = np.linalg.norm(vb)
    if na < 1e-9 or nb < 1e-9:
        return np.eye(3)
    va = va / na; vb = vb / nb
    cross = np.cross(va, vb)
    dot = float(np.clip(np.dot(va, vb), -1.0, 1.0))
    s = float(np.linalg.norm(cross))
    if s < 1e-9:
        if dot > 0.0:
            return np.eye(3)
        axis = np.cross(va, np.array([1.0, 0.0, 0.0]))
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(va, np.array([0.0, 1.0, 0.0]))
        axis = axis / np.linalg.norm(axis)
        return _axis_angle_matrix(axis, np.pi)
    axis = cross / s
    return _axis_angle_matrix(axis, float(np.arctan2(s, dot)))


def _axis_angle_matrix(axis, angle):
    x, y, z = axis
    c = np.cos(angle); s = np.sin(angle); C = 1.0 - c
    return np.array([
        [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
    ], dtype=np.float64)


def compute_target_basis(
    source_rest,
    source_parents,
    source_local_pose,
    target_rest,
    target_parents,
    source_map,
    world_from_source=None,
    target_object_rotation=None,
    alignments=None,
):
    """End-to-end: source local pose -> target local pose basis matrices.

    ``world_from_source`` is a 3x3 rotation mapping the source skeleton frame
    (e.g. OpenCV camera axes) into Blender world axes.  ``target_object_rotation``
    is the target armature object's world rotation; when present, world-space
    deltas are converted back into armature-object space before being applied
    to ``target_rest`` (which comes from ``bone.matrix_local``).
    """
    src_world = source_world(source_rest, source_parents, source_local_pose)
    deltas = world_deltas(src_world, source_rest)

    if world_from_source is not None:
        basis = validate_rotation(world_from_source, "world_from_source")
        deltas = [orthonormalize(basis @ d @ basis.T) for d in deltas]

    if target_object_rotation is not None:
        obj = validate_rotation(target_object_rotation, "target_object_rotation")
        deltas = [orthonormalize(obj.T @ d @ obj) for d in deltas]

    tgt_world, rel = target_world(deltas, source_map, target_rest, target_parents, alignments=alignments)
    return local_basis(tgt_world, rel, target_parents), tgt_world


def scale_root_translation(translation, source_leg_length, target_leg_length):
    """Scale root translation by the leg-length ratio (safe fallback 1.0)."""
    t = np.asarray(translation, dtype=np.float64).reshape(3)
    if not np.all(np.isfinite(t)):
        raise RetargetMathError("root translation contains NaN/Inf")
    if source_leg_length <= 1e-6 or target_leg_length <= 1e-6:
        return t.copy()
    return t * (float(target_leg_length) / float(source_leg_length))

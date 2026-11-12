"""Pure-numpy pose metrics: forward kinematics, 2D projection and input quality.

No bpy imports.  Used by the worker to flag half-body images and multi-person
inputs before the result reaches Blender.
"""

from __future__ import annotations

import numpy as np

from . import retarget_math


def forward_kinematics(rest_positions, parents, local_rotations, root_translation=None, rest_rotations=None):
    """Return joint positions (N,3) using the same chain as source_world()."""
    rest = np.asarray(rest_positions, dtype=np.float64)
    parents = [int(p) for p in parents]
    if rest_rotations is None:
        rest_rotations = [np.eye(3) for _ in parents]
    world_rot = retarget_math.source_world(
        rest_rotations, parents, local_rotations
    )
    pos = np.zeros_like(rest, dtype=np.float64)
    for i, parent in enumerate(parents):
        if parent < 0:
            pos[i] = rest[i]
        else:
            pos[i] = pos[parent] + world_rot[parent] @ (rest[i] - rest[parent])
    if root_translation is not None:
        pos = pos + np.asarray(root_translation, dtype=np.float64).reshape(1, 3)
    return pos


def project_points(camera, points, width, height):
    """Project camera-space points to pixel coordinates; return (uv, visible)."""
    pts = np.asarray(points, dtype=np.float64)
    m = np.asarray(camera["model_to_camera"], dtype=np.float64)
    cam = pts @ m[:3, :3].T + m[:3, 3]
    z = cam[:, 2]
    fx = float(camera["fx_px"])
    fy = float(camera.get("fy_px", fx))
    cx = float(camera["cx_px"])
    cy = float(camera["cy_px"])
    safe_z = np.where(np.abs(z) < 1e-9, 1e-9, z)
    uv = np.stack([fx * cam[:, 0] / safe_z + cx, fy * cam[:, 1] / safe_z + cy], axis=1)
    visible = (
        (z > 1e-6)
        & (uv[:, 0] >= 0.0) & (uv[:, 0] < float(width))
        & (uv[:, 1] >= 0.0) & (uv[:, 1] < float(height))
    )
    return uv, visible


def compute_input_quality(pose, bbox_xyxy=None, num_persons=1):
    """Build a compact, model-independent input quality report."""
    names = pose["source_skeleton"]["joint_names"]
    parents = pose["source_skeleton"]["parents"]
    rest = pose["source_skeleton"]["rest_positions"]
    rotations = pose["local_pose_rotations"]
    points = forward_kinematics(
        rest, parents, rotations, pose.get("root_translation"),
        pose["source_skeleton"]["rest_rotations"],
    )
    width = int(pose["image"]["width"])
    height = int(pose["image"]["height"])
    uv, visible = project_points(pose["camera"], points, width, height)
    ratio = float(visible.mean())

    lower_names = ("left_knee", "right_knee", "left_ankle", "right_ankle", "left_foot", "right_foot")
    lower_idx = [i for i, n in enumerate(names) if n in lower_names]
    lower_ratio = float(visible[lower_idx].mean()) if lower_idx else 1.0
    lower_visible = lower_ratio >= 0.5

    warnings = []
    if not lower_visible:
        warnings.append("lower body is outside the image; leg joints are unreliable")
    if num_persons and int(num_persons) > 1:
        warnings.append(f"detected {int(num_persons)} persons; only the largest bbox is used")

    edges = []
    if bbox_xyxy is not None:
        x0, y0, x1, y1 = [float(v) for v in bbox_xyxy]
        if y1 >= height * 0.98:
            edges.append("bottom")
        if y0 <= height * 0.02:
            edges.append("top")
        if x0 <= width * 0.02:
            edges.append("left")
        if x1 >= width * 0.98:
            edges.append("right")

    return {
        "visible_joint_ratio": round(ratio, 3),
        "lower_body_visible": bool(lower_visible),
        "lower_body_visible_ratio": round(lower_ratio, 3),
        "bbox_touches_edges": edges,
        "detected_persons": int(num_persons or 1),
        "warnings": warnings,
    }
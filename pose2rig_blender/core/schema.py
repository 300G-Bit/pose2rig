"""Validation and loading for the pose_result/v1 contract.

Pure Python + numpy; no bpy imports.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

import numpy as np

from . import retarget_math


class PoseSchemaError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


REQUIRED_TOP = [
    "schema_version",
    "request_id",
    "engine",
    "image",
    "conventions",
    "source_skeleton",
    "local_pose_rotations",
    "root_translation",
    "camera",
]


def _require(mapping, key, path):
    if key not in mapping:
        raise PoseSchemaError([f"{path}.{key} is required"])
    return mapping[key]


def _mat3(value, path):
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape != (3, 3):
        raise PoseSchemaError([f"{path}: expected 3x3, got {arr.shape}"])
    if not np.all(np.isfinite(arr)):
        raise PoseSchemaError([f"{path}: contains NaN/Inf"])
    if not np.allclose(arr.T @ arr, np.eye(3), atol=1e-3):
        raise PoseSchemaError([f"{path}: not orthonormal"])
    if np.linalg.det(arr) < 0.0:
        raise PoseSchemaError([f"{path}: determinant is negative"])
    return arr


def _mat4(value, path):
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape != (4, 4):
        raise PoseSchemaError([f"{path}: expected 4x4, got {arr.shape}"])
    if not np.all(np.isfinite(arr)):
        raise PoseSchemaError([f"{path}: contains NaN/Inf"])
    return arr


def _vec3(value, path):
    arr = np.asarray(value, dtype=np.float64).reshape(-1)
    if arr.shape != (3,) or not np.all(np.isfinite(arr)):
        raise PoseSchemaError([f"{path}: expected finite vec3"])
    return arr


def _positive_number(value, path):
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
        raise PoseSchemaError([f"{path}: expected positive number"])
    return float(value)


def validate_pose(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and return a normalized copy. Raises PoseSchemaError."""
    errors = []
    if not isinstance(data, dict):
        raise PoseSchemaError(["pose is not a JSON object"])

    for key in REQUIRED_TOP:
        if key not in data:
            errors.append(f"{key} is required")
    if errors:
        raise PoseSchemaError(errors)

    if data.get("schema_version") != "pose_result/v1":
        errors.append("schema_version must be 'pose_result/v1'")

    engine = data["engine"]
    if not isinstance(engine, dict):
        errors.append("engine must be an object")
    else:
        for key in ("id", "runtime"):
            if not isinstance(engine.get(key), str) or not engine.get(key):
                errors.append(f"engine.{key} must be a non-empty string")

    image = data["image"]
    w = _positive_number(image.get("width"), "image.width") if isinstance(image, dict) else 0
    h = _positive_number(image.get("height"), "image.height") if isinstance(image, dict) else 0

    conventions = data["conventions"]
    if not isinstance(conventions, dict):
        errors.append("conventions must be an object")
    else:
        if conventions.get("rotation") != "row_major_3x3":
            errors.append("conventions.rotation must be 'row_major_3x3'")
        frame = conventions.get("skeleton_frame", "world")
        if frame not in ("world", "camera"):
            errors.append("conventions.skeleton_frame must be 'world' or 'camera'")
        explicit = conventions.get("world_from_source")
        if explicit is not None:
            try:
                _mat3(explicit, "conventions.world_from_source")
            except PoseSchemaError as exc:
                errors.extend(exc.errors)

    skeleton = data["source_skeleton"]
    if not isinstance(skeleton, dict):
        raise PoseSchemaError(errors + ["source_skeleton must be an object"])
    names = skeleton.get("joint_names")
    parents = skeleton.get("parents")
    rest_positions = skeleton.get("rest_positions")
    rest_rotations = skeleton.get("rest_rotations")
    if not isinstance(names, list) or not all(isinstance(n, str) and n for n in names):
        errors.append("source_skeleton.joint_names must be a list of non-empty strings")
        names = []
    if not isinstance(parents, list):
        errors.append("source_skeleton.parents must be a list")
        parents = []
    try:
        retarget_math.validate_skeleton(names, parents)
    except Exception as exc:
        errors.append(f"source_skeleton: {exc}")

    if not isinstance(rest_positions, list) or len(rest_positions) != len(names):
        errors.append("source_skeleton.rest_positions length mismatch")
    else:
        for i, p in enumerate(rest_positions):
            try:
                _vec3(p, f"rest_positions[{i}]")
            except PoseSchemaError as exc:
                errors.extend(exc.errors)

    if not isinstance(rest_rotations, list) or len(rest_rotations) != len(names):
        errors.append("source_skeleton.rest_rotations length mismatch")
        rest_rotations = []
    else:
        for i, m in enumerate(rest_rotations):
            try:
                _mat3(m, f"rest_rotations[{i}]")
            except PoseSchemaError as exc:
                errors.extend(exc.errors)

    local_pose = data["local_pose_rotations"]
    if not isinstance(local_pose, list) or len(local_pose) != len(names):
        errors.append("local_pose_rotations length mismatch")
        local_pose = []
    else:
        for i, m in enumerate(local_pose):
            try:
                _mat3(m, f"local_pose_rotations[{i}]")
            except PoseSchemaError as exc:
                errors.extend(exc.errors)

    try:
        root_translation = _vec3(data["root_translation"], "root_translation")
    except PoseSchemaError as exc:
        errors.extend(exc.errors)
        root_translation = np.zeros(3)

    camera = data["camera"]
    if not isinstance(camera, dict):
        errors.append("camera must be an object")
        camera = {}
    for key in ("fx_px", "fy_px", "sensor_width_mm"):
        try:
            _positive_number(camera.get(key), f"camera.{key}")
        except PoseSchemaError as exc:
            errors.extend(exc.errors)
    for key in ("cx_px", "cy_px"):
        if not isinstance(camera.get(key), (int, float)):
            errors.append(f"camera.{key} must be a number")
    fit = camera.get("sensor_fit", "AUTO")
    if fit not in ("AUTO", "HORIZONTAL", "VERTICAL"):
        errors.append("camera.sensor_fit must be AUTO/HORIZONTAL/VERTICAL")
    try:
        model_to_camera = _mat4(camera.get("model_to_camera"), "camera.model_to_camera")
        if not np.allclose(model_to_camera[3], [0.0, 0.0, 0.0, 1.0], atol=1e-6):
            errors.append("camera.model_to_camera: last row must be [0,0,0,1]")
        top = model_to_camera[:3, :3]
        if not np.allclose(top.T @ top, np.eye(3), atol=1e-3):
            errors.append("camera.model_to_camera: top-left 3x3 is not orthonormal")
    except PoseSchemaError as exc:
        errors.extend(exc.errors)
        model_to_camera = np.eye(4)

    if errors:
        raise PoseSchemaError(errors)

    out = dict(data)
    out["image"] = {"width": int(round(w)), "height": int(round(h))}
    out["root_translation"] = root_translation.tolist()
    out["camera"] = dict(camera)
    out["camera"]["model_to_camera"] = model_to_camera.tolist()
    out["source_skeleton"] = {
        "joint_names": list(names),
        "parents": [int(p) for p in parents],
        "rest_positions": [list(map(float, p)) for p in rest_positions],
        "rest_rotations": [np.asarray(m, dtype=float).tolist() for m in rest_rotations],
    }
    out["local_pose_rotations"] = [np.asarray(m, dtype=float).tolist() for m in local_pose]
    return out


def load_pose(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        raise PoseSchemaError([f"pose file not found: {path}"])
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return validate_pose(data)

"""Camera and reference-image setup for Pose2Rig."""

from __future__ import annotations

import math
import os

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector


class CameraError(RuntimeError):
    pass


def _lens_mm(fx_px, fy_px, width, height, sensor_width_mm, sensor_fit):
    if sensor_fit == "HORIZONTAL":
        denom = float(width)
        focal = fx_px
    elif sensor_fit == "VERTICAL":
        denom = float(height)
        focal = fy_px
    else:
        denom = float(max(width, height))
        focal = fx_px
    if denom <= 0:
        raise CameraError("image has zero dimension")
    return float(focal) * float(sensor_width_mm) / denom


def _camera_pose_from_model_to_camera(m):
    """Return Blender camera world location and rotation from OpenCV-style
    model_to_camera (x right, y down, z forward)."""
    r = Matrix((m[0][:3], m[1][:3], m[2][:3]))
    t = Vector((m[0][3], m[1][3], m[2][3]))
    r_inv = r.inverted()
    # OpenCV camera world (x right, y down, z forward) -> Blender world
    # (x right, y depth, z up).  This must wrap both position and rotation.
    camera_to_blender = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))
    location = camera_to_blender @ (-(r_inv @ t))
    cv_local_to_camera = Matrix(((1, 0, 0), (0, -1, 0), (0, 0, -1)))
    rotation = camera_to_blender @ r_inv @ cv_local_to_camera
    return location, rotation


def create_or_update_camera(scene, pose, image_path=None, opacity=0.5, name="Pose2Rig_Camera", match_resolution=True):
    camera_data = bpy.data.cameras.get(name)
    if camera_data is None:
        camera_data = bpy.data.cameras.new(name)
    camera_obj = bpy.data.objects.get(name)
    if camera_obj is None:
        camera_obj = bpy.data.objects.new(name, camera_data)
        scene.collection.objects.link(camera_obj)
    camera_obj.data = camera_data

    cam = pose["camera"]
    width = int(pose["image"]["width"])
    height = int(pose["image"]["height"])
    if match_resolution:
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
    sensor_fit = cam.get("sensor_fit", "AUTO")
    camera_data.sensor_fit = sensor_fit
    camera_data.sensor_width = float(cam.get("sensor_width_mm", 36.0))
    camera_data.lens = _lens_mm(
        cam["fx_px"], cam.get("fy_px", cam["fx_px"]), width, height,
        camera_data.sensor_width, sensor_fit
    )
    # Principal point: Blender shift is expressed in sensor-width units.
    # For AUTO fit the reference dimension is max(W, H).
    max_dim = float(max(width, height))
    cx = float(cam.get("cx_px", width * 0.5))
    cy = float(cam.get("cy_px", height * 0.5))
    camera_data.shift_x = -(cx - width * 0.5) / max_dim
    camera_data.shift_y = (cy - height * 0.5) / max_dim

    location, rotation = _camera_pose_from_model_to_camera(cam["model_to_camera"])
    camera_obj.matrix_world = Matrix.Translation(location) @ rotation.to_4x4()
    scene.camera = camera_obj

    if image_path and os.path.isfile(image_path):
        _set_background(camera_data, image_path, opacity)
    return camera_obj


def _set_background(camera_data, image_path, opacity):
    camera_data.background_images.clear()
    bg = camera_data.background_images.new()
    try:
        bg.image = bpy.data.images.load(image_path, check_existing=True)
    except RuntimeError as exc:
        raise CameraError(f"cannot load reference image: {image_path}") from exc
    bg.alpha = max(0.0, min(1.0, float(opacity)))
    try:
        bg.display_depth = "FRONT"
    except (AttributeError, TypeError):
        pass


def project_point(scene, camera_obj, point):
    """Project a world-space point to normalized camera coordinates."""
    return world_to_camera_view(scene, camera_obj, Vector(point))


def delete_camera(scene, name="Pose2Rig_Camera"):
    obj = bpy.data.objects.get(name)
    if obj is not None:
        bpy.data.objects.remove(obj, do_unlink=True)
    data = bpy.data.cameras.get(name)
    if data is not None and data.users == 0:
        bpy.data.cameras.remove(data)

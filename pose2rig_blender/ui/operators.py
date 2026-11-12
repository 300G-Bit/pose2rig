"""Operators for Pose2Rig."""

from __future__ import annotations

import json
import os
import queue
import sys
import uuid
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from ..core import blender_retarget, camera_builder
from ..core.pose_state import restore_pose, snapshot_pose
from ..core.schema import PoseSchemaError, validate_pose
from ..ipc.client import WorkerClient
from ..worker.engines.model_layout import check_layout, format_missing

_STATE = {
    "queue": None,
    "client": None,
    "thread": None,
    "request_id": None,
    "snapshot": None,
    "armature": None,
    "scene_state": None,
    "applying": False,
}


def _package_name():
    return __package__.rsplit(".", 1)[0]


def _prefs(context):
    addon = context.preferences.addons.get(_package_name())
    return addon.preferences if addon else None


def _default_worker_python():
    base = Path(bpy.app.binary_path).parent
    version = f"{bpy.app.version[0]}.{bpy.app.version[1]}"
    candidates = [
        base / version / "python" / "bin" / "python.exe",
        base / "python" / "bin" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    if Path(sys.executable).name.lower().startswith("python"):
        return sys.executable
    return ""


def _worker_python(context):
    prefs = _prefs(context)
    value = getattr(prefs, "worker_python", "") if prefs else ""
    if value:
        return value
    return _default_worker_python()


def _server_script(context):
    prefs = _prefs(context)
    value = getattr(prefs, "worker_script", "") if prefs else ""
    if value:
        return value
    return str(Path(__file__).resolve().parent.parent / "worker" / "server.py")


def _image_size(path):
    img = bpy.data.images.load(path, check_existing=True)
    try:
        return int(img.size[0]), int(img.size[1])
    finally:
        # Do not remove the image: the camera background may reuse it.
        pass


def _error_text(response):
    err = response.get("error") or {}
    code = err.get("code", "unknown")
    message = err.get("message", "unknown worker error")
    details = err.get("details") or []
    if details:
        message += " | " + "; ".join(str(d) for d in details[:4])
    return f"{code}: {message}"


def _capture_ik_states(armature):
    return [
        (pb.name, c.name, bool(c.mute))
        for pb in armature.pose.bones for c in pb.constraints if c.type == "IK"
    ]


def _restore_ik_states(armature, states):
    if not states:
        return
    for bone_name, constraint_name, mute in states:
        pb = armature.pose.bones.get(bone_name)
        if pb is None:
            continue
        constraint = pb.constraints.get(constraint_name)
        if constraint is not None:
            constraint.mute = mute


def _capture_scene_state(scene):
    return {
        "resolution": (
            int(scene.render.resolution_x),
            int(scene.render.resolution_y),
            int(scene.render.resolution_percentage),
        ),
        "camera": scene.camera,
        "plugin_camera": bpy.data.objects.get("Pose2Rig_Camera"),
    }


def _restore_scene_state(scene, state):
    if not state:
        return
    scene.render.resolution_x = state["resolution"][0]
    scene.render.resolution_y = state["resolution"][1]
    scene.render.resolution_percentage = state["resolution"][2]
    previous_camera = state.get("camera")
    try:
        if previous_camera is not None and previous_camera.name in bpy.data.objects:
            scene.camera = previous_camera
        else:
            scene.camera = None
    except ReferenceError:
        scene.camera = None
    # If Pose2Rig created the camera during this preview, remove it on cancel.
    plugin_before = state.get("plugin_camera")
    plugin_now = bpy.data.objects.get("Pose2Rig_Camera")
    if plugin_before is None and plugin_now is not None:
        camera_builder.delete_camera(scene)


def _apply_pose(context, pose, settings, take_snapshot=True):
    arm = settings.target_armature
    if arm is None:
        raise RuntimeError("Target Rig is not set")
    if take_snapshot and _STATE["snapshot"] is None:
        _STATE["snapshot"] = snapshot_pose(arm)
        _STATE["armature"] = arm
        _STATE["scene_state"] = _capture_scene_state(context.scene)
    if _STATE.get("ik_states") is None:
        _STATE["ik_states"] = _capture_ik_states(arm)
    options = {
        "shoulder_relax": settings.shoulder_relax,
        "spine_influence": settings.spine_influence,
        "ground_snap": settings.ground_snap,
        "mapping_mode": getattr(settings, "mapping_mode", "AUTO"),
    }
    info = blender_retarget.apply_pose(arm, pose, settings.preset, options)
    if settings.auto_camera:
        image_path = settings.image_path if settings.show_reference else None
        camera_builder.create_or_update_camera(
            context.scene,
            pose,
            image_path=image_path,
            opacity=settings.opacity,
        )
    warnings = []
    diagnostics = pose.get("diagnostics") or {}
    warnings.extend(str(w) for w in (diagnostics.get("warnings") or []))
    quality = pose.get("input_quality") or {}
    warnings.extend(str(w) for w in (quality.get("warnings") or []))
    settings.last_warnings = " | ".join(dict.fromkeys(warnings))
    settings.last_pose_json = json.dumps(pose)
    mode = options.get("mapping_mode", "AUTO")
    suffix = ""
    if mode == "UPPER_BODY" or (mode == "AUTO" and quality.get("lower_body_visible") is False):
        suffix = ", upper body"
    settings.status = f"Done: {info['mapped_bones']} bones ({info['preset']}{suffix})"
    return info


def _poll_generate():
    q = _STATE.get("queue")
    if q is None:
        return None
    try:
        response = q.get_nowait()
    except queue.Empty:
        thread = _STATE.get("thread")
        if thread is not None and thread.is_alive():
            return 0.1
        settings = getattr(bpy.context.scene, "pose2rig", None)
        if settings:
            settings.status = "Error: worker produced no response"
        _STATE["queue"] = None
        return None

    _STATE["queue"] = None
    settings = getattr(bpy.context.scene, "pose2rig", None)
    if settings is None:
        return None
    if response.get("type") == "error":
        settings.status = "Error: " + _error_text(response)
        return None
    if response.get("type") == "cancelled":
        settings.status = "Cancelled"
        return None
    if response.get("type") != "result":
        settings.status = "Error: unexpected worker response"
        return None
    try:
        settings.progress = 0.5
        pose = validate_pose(response["pose"])
        _apply_pose(bpy.context, pose, settings, take_snapshot=True)
        settings.progress = 1.0
    except (PoseSchemaError, Exception) as exc:  # noqa: BLE001
        settings.progress = 0.0
        settings.status = f"Error: {type(exc).__name__}: {exc}"
    return None


def _start_generate(context, settings):
    if _STATE.get("queue") is not None:
        settings.status = "Already running"
        return
    image_path = bpy.path.abspath(settings.image_path or "")
    if not image_path or not os.path.isfile(image_path):
        settings.status = "Error: choose an existing reference image"
        return
    if settings.target_armature is None:
        settings.status = "Error: choose a target armature"
        return
    arm = settings.target_armature
    if _STATE["snapshot"] is not None and _STATE["armature"] is not arm:
        settings.status = "Error: Apply or Cancel the previous rig preview first"
        return
    if _STATE["snapshot"] is None:
        _STATE["snapshot"] = snapshot_pose(arm)
        _STATE["armature"] = arm
        _STATE["scene_state"] = _capture_scene_state(context.scene)
    try:
        width, height = _image_size(image_path)
    except Exception as exc:  # noqa: BLE001
        settings.status = f"Error: cannot read image: {exc}"
        return

    request_id = str(uuid.uuid4())
    prefs = _prefs(context)
    request = {
        "type": "infer",
        "request_id": request_id,
        "engine": settings.engine,
        "image_path": image_path,
        "options": {
            "image_width": width,
            "image_height": height,
            "include_fingers": settings.include_fingers,
            "model_dir": getattr(prefs, "model_dir", "") if prefs else "",
            "repo_dir": getattr(prefs, "repo_dir", "") if prefs else "",
            "variant": getattr(prefs, "variant", "s32") if prefs else "s32",
            "device": "cuda",
        },
    }
    q = queue.Queue()
    client = WorkerClient(_worker_python(context), _server_script(context))
    timeout_s = float(getattr(prefs, "worker_timeout", 600) if prefs else 600)
    thread = client.submit(request, q, timeout_s=timeout_s)
    _STATE.update({"queue": q, "client": client, "thread": thread, "request_id": request_id})
    settings.status = "Running..."
    settings.progress = 0.05
    bpy.app.timers.register(_poll_generate, first_interval=0.1)


def reapply_last_pose(context, settings):
    if _STATE.get("applying"):
        return
    if not settings.last_pose_json or settings.target_armature is None:
        return
    if _STATE.get("armature") is not settings.target_armature:
        return
    try:
        _STATE["applying"] = True
        pose = validate_pose(json.loads(settings.last_pose_json))
        _apply_pose(context, pose, settings, take_snapshot=False)
    except Exception as exc:  # noqa: BLE001
        settings.status = f"Error: {type(exc).__name__}: {exc}"
    finally:
        _STATE["applying"] = False


class POSE2RIG_OT_generate(Operator):
    bl_idname = "pose2rig.generate"
    bl_label = "Generate 3D Pose"
    bl_description = "Run the worker and preview the pose"
    bl_options = {"REGISTER"}

    def execute(self, context):
        _start_generate(context, context.scene.pose2rig)
        return {"FINISHED"}


class POSE2RIG_OT_apply(Operator):
    bl_idname = "pose2rig.apply"
    bl_label = "Apply Pose"
    bl_description = "Keep the previewed pose and push an undo step"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.pose2rig
        if _STATE.get("snapshot") is None:
            settings.status = "Nothing to apply"
            return {"CANCELLED"}
        bpy.ops.ed.undo_push(message="Pose2Rig Apply")
        _STATE["snapshot"] = None
        _STATE["scene_state"] = None
        settings.status = "Applied"
        return {"FINISHED"}


class POSE2RIG_OT_cancel(Operator):
    bl_idname = "pose2rig.cancel"
    bl_label = "Cancel Preview"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.pose2rig
        snap = _STATE.get("snapshot")
        arm = _STATE.get("armature")
        scene_state = _STATE.get("scene_state")
        if snap and arm:
            restore_pose(arm, snap)
            _restore_scene_state(context.scene, scene_state)
            settings.status = "Cancelled"
        else:
            settings.status = "Nothing to cancel"
        _STATE["snapshot"] = None
        _STATE["scene_state"] = None
        _STATE["ik_states"] = None
        return {"FINISHED"}


class POSE2RIG_OT_reset(Operator):
    bl_idname = "pose2rig.reset"
    bl_label = "Reset Pose"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings = context.scene.pose2rig
        arm = settings.target_armature
        if arm:
            blender_retarget.clear_pose(arm)
            _restore_ik_states(arm, _STATE.get("ik_states"))
        _restore_scene_state(context.scene, _STATE.get("scene_state"))
        camera_builder.delete_camera(context.scene)
        settings.last_pose_json = ""
        settings.last_warnings = ""
        settings.status = "Reset"
        _STATE["snapshot"] = None
        _STATE["scene_state"] = None
        _STATE["ik_states"] = None
        return {"FINISHED"}


class POSE2RIG_OT_probe_engine(Operator):
    bl_idname = "pose2rig.probe_engine"
    bl_label = "Check Engine Files"
    bl_description = "Check the configured SMPLer-X model directory"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.pose2rig
        prefs = _prefs(context)
        if prefs is None:
            settings.status = "Error: add-on preferences not found"
            return {"CANCELLED"}
        layout = check_layout(prefs.model_dir, prefs.variant)
        if layout["ready"]:
            settings.status = f"SMPLer-X {prefs.variant}: layout ready"
        else:
            settings.status = "SMPLer-X missing files: " + format_missing(layout, limit=3).replace("\n", " | ")
        return {"FINISHED"}


class POSE2RIG_OT_save_pose(Operator, ExportHelper):
    bl_idname = "pose2rig.save_pose"
    bl_label = "Save Pose JSON"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        settings = context.scene.pose2rig
        if not settings.last_pose_json:
            settings.status = "No pose to save"
            return {"CANCELLED"}
        with open(self.filepath, "w", encoding="utf-8") as handle:
            handle.write(settings.last_pose_json)
        settings.last_result_path = self.filepath
        settings.status = f"Saved {os.path.basename(self.filepath)}"
        return {"FINISHED"}


class POSE2RIG_OT_load_pose(Operator, ImportHelper):
    bl_idname = "pose2rig.load_pose"
    bl_label = "Load Pose JSON"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        settings = context.scene.pose2rig
        try:
            with open(self.filepath, "r", encoding="utf-8") as handle:
                pose = validate_pose(json.load(handle))
            _apply_pose(context, pose, settings, take_snapshot=True)
            settings.last_result_path = self.filepath
        except Exception as exc:  # noqa: BLE001
            settings.status = f"Error: {type(exc).__name__}: {exc}"
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = [
    POSE2RIG_OT_generate,
    POSE2RIG_OT_apply,
    POSE2RIG_OT_cancel,
    POSE2RIG_OT_reset,
    POSE2RIG_OT_probe_engine,
    POSE2RIG_OT_save_pose,
    POSE2RIG_OT_load_pose,
]

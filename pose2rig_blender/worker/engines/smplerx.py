"""SMPLer-X adapter.

This module converts SMPLer-X predictions into pose_result/v1.  The network
bridge is intentionally isolated: it needs a separate Python environment with
torch/mmdet and the user's SMPL-X model files.  The conversion path itself is
pure numpy and can be tested without a GPU.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from ...core.pose_metrics import compute_input_quality
from .base import Engine, EngineUnavailable
from .model_layout import check_layout, format_missing

SKELETON_PATH = Path(__file__).resolve().parents[2] / "assets" / "skeleton" / "smplx_rest_skeleton.json"

# SMPL-X template T-pose is Y-up; the prediction pipeline uses OpenCV camera
# axes (x right, y down, z forward).  R_x(180) maps template Y-up to camera
# Y-down and is the source skeleton's world rest orientation.
REST_CAM = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]], dtype=np.float64)
CAMERA_TO_BLENDER = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]], dtype=np.float64)


def _load_skeleton():
    path = Path(os.environ.get("POSE2RIG_SMPLX_SKELETON", str(SKELETON_PATH)))
    if not path.is_file():
        raise EngineUnavailable(
            "SMPL-X rest skeleton not found: "
            f"{path}. The skeleton is generated locally from the licensed "
            "SMPL-X model and is not distributed with this repository. Run "
            "python tools/make_smplx_rest_skeleton.py --model <SMPLX_NEUTRAL.npz> "
            "or set POSE2RIG_SMPLX_SKELETON."
        )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def axis_angle_to_matrix(vec):
    """Rodrigues formula for one 3-vector; returns a 3x3 numpy array."""
    v = np.asarray(vec, dtype=np.float64).reshape(3)
    theta = float(np.linalg.norm(v))
    if theta < 1e-8:
        return np.eye(3)
    axis = v / theta
    x, y, z = axis
    c, s = math.cos(theta), math.sin(theta)
    C = 1.0 - c
    return np.array([
        [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
    ], dtype=np.float64)


def _first(value, default=0.0):
    arr = np.asarray(value, dtype=np.float64)
    if arr.size == 0:
        return float(default)
    return float(arr.reshape(-1)[0])


def prediction_to_pose(prediction: dict, image_width: int, image_height: int,
                       bbox_xyxy=None, include_fingers=True, engine_meta=None) -> dict:
    """Convert one SMPLer-X prediction dict to pose_result/v1.

    Expected keys (all optional except root/body):
      smplx_root_pose (3,), smplx_body_pose (21,3),
      smplx_lhand_pose (15,3), smplx_rhand_pose (15,3), smplx_jaw_pose (3,),
      cam_trans (3,), focal (2,), princpt (2,)
    """
    skeleton = _load_skeleton()
    names = skeleton["joint_names"]
    parents = skeleton["parents"]
    rest_positions = skeleton["rest_positions"]
    rest_rotations = skeleton["rest_rotations"]

    # SMPLer-X inference.py writes global_orient/body_pose/... while other
    # adapters use smplx_* names.  Support both.
    root = np.asarray(prediction.get("smplx_root_pose", prediction.get("global_orient", [0, 0, 0])), dtype=np.float64).reshape(3)
    body = np.asarray(prediction.get("smplx_body_pose", prediction.get("body_pose", np.zeros((21, 3)))), dtype=np.float64).reshape(-1, 3)
    lhand = np.asarray(prediction.get("smplx_lhand_pose", prediction.get("left_hand_pose", np.zeros((15, 3)))), dtype=np.float64).reshape(-1, 3)
    rhand = np.asarray(prediction.get("smplx_rhand_pose", prediction.get("right_hand_pose", np.zeros((15, 3)))), dtype=np.float64).reshape(-1, 3)
    jaw = np.asarray(prediction.get("smplx_jaw_pose", prediction.get("jaw_pose", [0, 0, 0])), dtype=np.float64).reshape(3)

    local = []
    # global_orient is a world rotation from the SMPL-X rest frame to the
    # camera frame.  The skeleton rest orientation is REST_CAM, so store the
    # root local rotation relative to that rest orientation.
    local.append(REST_CAM.T @ axis_angle_to_matrix(root))
    for i in range(21):
        local.append(axis_angle_to_matrix(body[i] if i < len(body) else np.zeros(3)))
    local.append(axis_angle_to_matrix(jaw))
    local.append(np.eye(3))
    local.append(np.eye(3))
    for i in range(15):
        local.append(axis_angle_to_matrix(lhand[i] if i < len(lhand) else np.zeros(3)))
    for i in range(15):
        local.append(axis_angle_to_matrix(rhand[i] if i < len(rhand) else np.zeros(3)))
    if len(local) != len(names):
        raise ValueError(f"local rotation count {len(local)} != skeleton joints {len(names)}")

    if not include_fingers:
        for i in range(25, 55):
            local[i] = np.eye(3)

    w = int(image_width)
    h = int(image_height)
    quality_bbox = None
    if bbox_xyxy is not None:
        x0, y0, a, b = [float(v) for v in bbox_xyxy]
        # SMPLer-X process_bbox returns [x, y, w, h]; other adapters use xyxy.
        if a < x0 or b < y0:
            x1, y1 = x0 + a, y0 + b
        else:
            x1, y1 = a, b
        bbox_w = max(1.0, x1 - x0)
        bbox_h = max(1.0, y1 - y0)
        bbox_cx = (x0 + x1) * 0.5
        bbox_cy = (y0 + y1) * 0.5
        quality_bbox = (x0, y0, x1, y1)
    else:
        bbox_w, bbox_h = float(w), float(h)
        bbox_cx, bbox_cy = w * 0.5, h * 0.5

    focal = prediction.get("focal")
    if focal is not None:
        fx = _first(focal)
        fy = _first(focal)
    else:
        # SMPLer-X uses a virtual focal of 5000 on a 256x256 crop and scales by bbox width.
        fx = 5000.0 / 256.0 * bbox_w
        fy = fx
    princpt = prediction.get("princpt")
    if princpt is not None and len(princpt) >= 2:
        cx, cy = float(princpt[0]), float(princpt[1])
    else:
        cx, cy = bbox_cx, bbox_cy

    cam_trans = np.asarray(prediction.get("cam_trans", prediction.get("transl", [0, 0, 3.0])), dtype=np.float64).reshape(3)
    model_to_camera = np.eye(4, dtype=np.float64)
    model_to_camera[:3, 3] = cam_trans

    result = {
        "schema_version": "pose_result/v1",
        "request_id": str(prediction.get("request_id", "smplerx")),
        "engine": {
            "id": "smplerx",
            "runtime": str((engine_meta or {}).get("runtime", "torch")),
            "weights_sha256": (engine_meta or {}).get("weights_sha256"),
            "source_revision": (engine_meta or {}).get("source_revision"),
        },
        "image": {"width": w, "height": h, "sha256": str(prediction.get("image_sha256", ""))},
        "conventions": {
            "units": "m",
            "rotation": "row_major_3x3",
            "camera": "x_right_y_down_z_forward",
            "handedness": "right",
            "skeleton_frame": "camera",
            "world_from_source": CAMERA_TO_BLENDER.tolist(),
        },
        "source_skeleton": {
            "joint_names": names,
            "parents": parents,
            "rest_positions": rest_positions,
            "rest_rotations": [REST_CAM.tolist() for _ in names],
        },
        "local_pose_rotations": [m.tolist() for m in local],
        "root_translation": [0.0, 0.0, 0.0],
        "camera": {
            "fx_px": fx,
            "fy_px": fy,
            "cx_px": cx,
            "cy_px": cy,
            "sensor_fit": "AUTO",
            "sensor_width_mm": 36.0,
            "model_to_camera": model_to_camera.tolist(),
        },
        "hands": {"enabled": bool(include_fingers), "confidence": None},
        "diagnostics": {"timings_ms": {}, "warnings": []},
    }
    quality = compute_input_quality(
        result,
        bbox_xyxy=quality_bbox,
        num_persons=prediction.get("num_persons", prediction.get("detected_persons", 1)),
    )
    result["input_quality"] = quality
    result["diagnostics"]["warnings"].extend(quality.get("warnings") or [])
    return result


class SmplerXEngine(Engine):
    id = "smplerx"

    def __init__(self, model_dir: str | None = None, device: str = "cuda", variant: str = "s32",
                 repo_dir: str | None = None):
        self.model_dir = str(model_dir or "")
        self.device = device
        self.variant = variant.lower()
        if repo_dir is None:
            repo_dir = str(Path(__file__).resolve().parents[3] / "_research" / "repos" / "SMPLer-X")
        self.repo_dir = str(repo_dir)

    def probe(self) -> dict:
        return check_layout(self.model_dir, self.variant)

    def _run_reference_inference(self, image_path: str, options: dict) -> dict:
        repo_main = Path(self.repo_dir) / "main"
        inference = repo_main / "inference.py"
        if not inference.is_file():
            raise EngineUnavailable(f"SMPLer-X repo not found: {self.repo_dir}")
        frame_dir = tempfile.mkdtemp(prefix="pose2rig_frames_")
        out_dir = tempfile.mkdtemp(prefix="pose2rig_out_")
        try:
            target_image = Path(frame_dir) / "000000.jpg"
            converted = False
            if Path(image_path).suffix.lower() in (".webp", ".png", ".bmp", ".tif", ".tiff"):
                try:
                    from PIL import Image
                    Image.open(image_path).convert("RGB").save(target_image, "JPEG", quality=95)
                    converted = True
                except Exception:
                    converted = False
            if not converted:
                shutil.copy2(image_path, target_image)
            cmd = [
                sys.executable, "inference.py",
                "--num_gpus", "1",
                "--pretrained_model", f"smpler_x_{self.variant}",
                "--img_path", frame_dir,
                "--output_folder", out_dir,
                "--start", "0",
                "--end", "1",
                "--testset", "EHF",
            ]
            proc = subprocess.run(
                cmd,
                cwd=str(repo_main),
                capture_output=True,
                text=True,
                timeout=float(options.get("timeout_s", 900)),
            )
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "")[-4000:]
                raise EngineUnavailable(f"SMPLer-X inference failed (exit {proc.returncode}):\n{tail}")
            npz_files = sorted((Path(out_dir) / "smplx").glob("*.npz"))
            if not npz_files:
                raise EngineUnavailable("SMPLer-X inference produced no smplx npz output")
            with np.load(npz_files[0], allow_pickle=True) as data:
                prediction = {key: data[key] for key in data.files}
            meta_files = sorted((Path(out_dir) / "meta").glob("*.json"))
            if meta_files:
                with open(meta_files[0], "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
                for key in ("focal", "princpt", "bbox", "bbox_mmdet", "num_persons"):
                    if key in meta:
                        prediction[key] = meta[key]
            with open(image_path, "rb") as handle:
                prediction["image_sha256"] = hashlib.sha256(handle.read()).hexdigest()
            return prediction
        except subprocess.TimeoutExpired as exc:
            raise EngineUnavailable(f"SMPLer-X inference timed out: {exc}") from exc
        finally:
            shutil.rmtree(frame_dir, ignore_errors=True)
            shutil.rmtree(out_dir, ignore_errors=True)

    def infer(self, image_path: str, options: dict) -> dict:
        t0 = time.perf_counter()
        layout = self.probe()
        if not layout["ready"]:
            raise EngineUnavailable(format_missing(layout))
        t1 = time.perf_counter()
        prediction = self._run_reference_inference(image_path, options)
        t2 = time.perf_counter()
        bbox = prediction.get("bbox") or options.get("bbox_xyxy")
        pose = prediction_to_pose(
            prediction,
            int(options.get("image_width") or 0) or 1,
            int(options.get("image_height") or 0) or 1,
            bbox_xyxy=bbox,
            include_fingers=bool(options.get("include_fingers", True)),
            engine_meta={
                "runtime": "torch",
                "weights_sha256": options.get("weights_sha256"),
                "source_revision": "064baef0e4ab5277a3297691bc1d46ea5412586f",
            },
        )
        t3 = time.perf_counter()
        pose["diagnostics"]["timings_ms"] = {
            "probe": round((t1 - t0) * 1000.0, 1),
            "inference": round((t2 - t1) * 1000.0, 1),
            "convert": round((t3 - t2) * 1000.0, 1),
            "total": round((t3 - t0) * 1000.0, 1),
        }
        return pose

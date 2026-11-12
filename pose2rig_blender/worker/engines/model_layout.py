"""Check the SMPLer-X on-disk layout without importing torch.

Required for inference (SMPLer-X's human_models.py instantiates SMPL-X and
SMPL for all three genders, and opens the correspondence files):
  smplx/SMPLX_NEUTRAL.npz, SMPLX_MALE.npz, SMPLX_FEMALE.npz
  smplx/SMPLX_to_J14.pkl, MANO_SMPLX_vertex_ids.pkl, SMPL-X__FLAME_vertex_ids.npy
  smpl/SMPL_NEUTRAL.pkl, SMPL_MALE.pkl, SMPL_FEMALE.pkl
  pretrained_models/smpler_x_<variant>.pth.tar
  pretrained_models/mmdet/faster_rcnn_...pth + config

Optional: SMPLX_*.pkl (the v1.1 bundle ships them, but the smplx loader uses
the .npz files), ViTPose checkpoints (training only, not demo inference).
"""

from __future__ import annotations

import os
from pathlib import Path

VARIANTS = {
    "s32": {"backbone": "vitpose_small", "params_m": 32},
    "b32": {"backbone": "vitpose_base", "params_m": 103},
    "l32": {"backbone": "vitpose_large", "params_m": 327},
    "h32": {"backbone": "vitpose_huge", "params_m": 662},
}


def _p(root, *parts):
    return str(Path(root).joinpath(*parts))


def required_files(model_dir: str, variant: str = "s32"):
    variant = variant.lower()
    if variant not in VARIANTS:
        raise ValueError(f"unknown SMPLer-X variant: {variant}")
    return [
        _p(model_dir, "pretrained_models", f"smpler_x_{variant}.pth.tar"),
        _p(model_dir, "pretrained_models", "mmdet", "faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth"),
        _p(model_dir, "pretrained_models", "mmdet", "mmdet_faster_rcnn_r50_fpn_coco.py"),
        _p(model_dir, "common", "utils", "human_model_files", "smplx", "SMPLX_NEUTRAL.npz"),
        _p(model_dir, "common", "utils", "human_model_files", "smplx", "SMPLX_MALE.npz"),
        _p(model_dir, "common", "utils", "human_model_files", "smplx", "SMPLX_FEMALE.npz"),
        _p(model_dir, "common", "utils", "human_model_files", "smplx", "SMPLX_to_J14.pkl"),
        _p(model_dir, "common", "utils", "human_model_files", "smplx", "MANO_SMPLX_vertex_ids.pkl"),
        _p(model_dir, "common", "utils", "human_model_files", "smplx", "SMPL-X__FLAME_vertex_ids.npy"),
        _p(model_dir, "common", "utils", "human_model_files", "smpl", "SMPL_NEUTRAL.pkl"),
        _p(model_dir, "common", "utils", "human_model_files", "smpl", "SMPL_MALE.pkl"),
        _p(model_dir, "common", "utils", "human_model_files", "smpl", "SMPL_FEMALE.pkl"),
    ]


def optional_files(model_dir: str):
    base = Path(model_dir).joinpath("common", "utils", "human_model_files")
    return [
        str(base / "smplx" / "SMPLX_NEUTRAL.pkl"),
        str(base / "smplx" / "SMPLX_MALE.pkl"),
        str(base / "smplx" / "SMPLX_FEMALE.pkl"),
        str(Path(model_dir) / "pretrained_models" / "vitpose_small.pth"),
    ]


def check_layout(model_dir: str, variant: str = "s32") -> dict:
    if not model_dir:
        return {"ready": False, "model_dir": "", "variant": variant, "missing": ["model_dir is empty"], "found": []}
    files = required_files(model_dir, variant)
    found = [p for p in files if os.path.isfile(p)]
    missing = [p for p in files if not os.path.isfile(p)]
    return {
        "ready": not missing,
        "model_dir": str(Path(model_dir)),
        "variant": variant.lower(),
        "missing": missing,
        "found": found,
        "optional_missing": [p for p in optional_files(model_dir) if not os.path.isfile(p)],
    }


def format_missing(layout: dict, limit: int = 8) -> str:
    missing = layout.get("missing") or []
    if not missing:
        return "layout ready"
    lines = [f"SMPLer-X layout is incomplete for variant {layout.get('variant')}: "]
    for item in missing[:limit]:
        lines.append("  - " + item)
    if len(missing) > limit:
        lines.append(f"  ... and {len(missing) - limit} more")
    return "\n".join(lines)

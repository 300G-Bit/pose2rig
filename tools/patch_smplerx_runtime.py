"""Apply the small compatibility patches needed by SMPLer-X on Windows/Python 3.8.

Run with the SMPLer-X venv Python:
  _envs/smplerx/Scripts/python.exe tools/patch_smplerx_runtime.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_envs" / "smplerx" / "Lib" / "site-packages"
REPO = ROOT / "_research" / "repos" / "SMPLer-X"


def replace(path: Path, old: str, new: str, label: str):
    if not path.is_file():
        print(f"SKIP {label}: {path} missing")
        return
    text = path.read_text(encoding="utf-8")
    if old not in text:
        print(f"OK   {label}: already patched or text absent")
        return
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"PATCH {label}: {path}")


def main() -> int:
    conv = SITE / "torchgeometry" / "core" / "conversions.py"
    replace(conv,
            "    mask_c1 = mask_d2 * (1 - mask_d0_d1)\n"
            "    mask_c2 = (1 - mask_d2) * mask_d0_nd1\n"
            "    mask_c3 = (1 - mask_d2) * (1 - mask_d0_nd1)",
            "    mask_c1 = mask_d2 * (~mask_d0_d1)\n"
            "    mask_c2 = (~mask_d2) * mask_d0_nd1\n"
            "    mask_c3 = (~mask_d2) * (~mask_d0_nd1)",
            "torchgeometry bool subtraction")

    cfg = REPO / "main" / "config.py"
    replace(cfg,
            "        # Save\n"
            "        cfg_save = MMConfig(self.__dict__)\n"
            "        cfg_save.dump(osp.join(self.code_dir,'config_base.py'))",
            "        # Save disabled for Pose2Rig (Windows paths break mmcv yapf dump).",
            "SMPLer-X config dump")

    inf = REPO / "main" / "inference.py"
    replace(inf,
            "    from utils.preprocessing import load_img, process_bbox, generate_patch_image\n"
            "    from utils.vis import render_mesh, save_obj\n"
            "    from utils.human_models import smpl_x",
            "    from utils.preprocessing import load_img, process_bbox, generate_patch_image\n"
            "    try:\n"
            "        from utils.vis import render_mesh, save_obj\n"
            "    except Exception:\n"
            "        render_mesh = None\n"
            "        save_obj = None\n"
            "    from utils.human_models import smpl_x",
            "SMPLer-X optional vis import")
    replace(inf,
            "            vis_img = render_mesh(vis_img, mesh, smpl_x.face, {'focal': focal, 'princpt': princpt},\n"
            "                                  mesh_as_vertices=args.show_verts)",
            "            if render_mesh is not None:\n"
            "                vis_img = render_mesh(vis_img, mesh, smpl_x.face, {'focal': focal, 'princpt': princpt},\n"
            "                                      mesh_as_vertices=args.show_verts)",
            "SMPLer-X optional render")
    replace(inf,
            "        mmdet_box = process_mmdet_results(mmdet_results, cat_id=0, multi_person=True)\n",
            "        mmdet_box = process_mmdet_results(mmdet_results, cat_id=0, multi_person=True)\n"
            "        num_persons = len(mmdet_box[0]) if len(mmdet_box) > 0 else 0\n",
            "SMPLer-X person count")
    replace(inf,
            "                    'bbox_id': bbox_id,",
            "                    'num_persons': int(num_persons),\n"
            "                    'bbox_id': bbox_id,",
            "SMPLer-X meta person count")
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

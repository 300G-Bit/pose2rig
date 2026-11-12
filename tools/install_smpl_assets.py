"""Install user-provided SMPL/SMPL-X files into the SMPLer-X model tree.

Handles the common nested archives in models_smplx_v1_1.zip and extracts only
the files SMPLer-X needs.  Does not download anything; place login-gated
archives where this script can read them.

Usage:
  python tools/install_smpl_assets.py --models-dir _models/smplerx ^
      --smplx-zip path/to/models_smplx_v1_1.zip ^
      --corr-zip path/to/smplx_mano_flame_correspondences.zip ^
      --smpl-zip path/to/SMPL_python_v.1.1.0.zip ^
      --j14 path/to/SMPLX_to_J14.pkl
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SMPLX_NAMES = [
    "SMPLX_NEUTRAL.npz", "SMPLX_MALE.npz", "SMPLX_FEMALE.npz",
    "SMPLX_NEUTRAL.pkl", "SMPLX_MALE.pkl", "SMPLX_FEMALE.pkl",
    "SMPLX_to_J14.pkl", "MANO_SMPLX_vertex_ids.pkl", "SMPL-X__FLAME_vertex_ids.npy",
]
SMPL_NAMES = ["SMPL_NEUTRAL.pkl", "SMPL_MALE.pkl", "SMPL_FEMALE.pkl"]
SMPL_ALIASES = {
    "SMPL_NEUTRAL.pkl": ["basicmodel_neutral_lbs_10_207_0_v1.1.0.pkl"],
    "SMPL_MALE.pkl": ["basicmodel_m_lbs_10_207_0_v1.1.0.pkl"],
    "SMPL_FEMALE.pkl": ["basicmodel_f_lbs_10_207_0_v1.1.0.pkl"],
}


def _extract_zip(zip_path: Path, out_dir: Path):
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)
    # Some SMPL-X releases contain nested platform/format zips.
    for nested in list(out_dir.rglob("*.zip")):
        target = nested.with_name(nested.stem + "_extracted")
        target.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(nested) as zf:
                zf.extractall(target)
        except zipfile.BadZipFile:
            continue


def _collect(root: Path, names, aliases=None):
    aliases = aliases or {}
    found = {}
    for name in names:
        candidates = list(root.rglob(name))
        for alias in aliases.get(name, []):
            candidates += list(root.rglob(alias))
        if candidates:
            found[name] = candidates[0]
    return found


def _copy(found, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for name, src in found.items():
        dst = destination / name
        shutil.copy2(src, dst)
        copied.append(str(dst))
    return copied


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-dir", default=str(ROOT / "_models" / "smplerx"))
    parser.add_argument("--smplx-zip", default=None)
    parser.add_argument("--corr-zip", default=None)
    parser.add_argument("--smpl-zip", default=None)
    parser.add_argument("--j14", default=None)
    parser.add_argument("--source-dir", default=None, help="Optional folder with already extracted files")
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    smplx_dir = models_dir / "common" / "utils" / "human_model_files" / "smplx"
    smpl_dir = models_dir / "common" / "utils" / "human_model_files" / "smpl"
    smplx_dir.mkdir(parents=True, exist_ok=True)
    smpl_dir.mkdir(parents=True, exist_ok=True)

    temp_dirs = []
    try:
        roots = []
        if args.smplx_zip:
            tmp = Path(tempfile.mkdtemp(prefix="smplx_zip_")); temp_dirs.append(tmp)
            _extract_zip(Path(args.smplx_zip), tmp); roots.append(tmp)
        if args.corr_zip:
            tmp = Path(tempfile.mkdtemp(prefix="corr_zip_")); temp_dirs.append(tmp)
            _extract_zip(Path(args.corr_zip), tmp); roots.append(tmp)
        if args.smpl_zip:
            tmp = Path(tempfile.mkdtemp(prefix="smpl_zip_")); temp_dirs.append(tmp)
            _extract_zip(Path(args.smpl_zip), tmp); roots.append(tmp)
        if args.source_dir:
            roots.append(Path(args.source_dir))

        smplx_found = {}
        smpl_found = {}
        for root in roots:
            smplx_found.update(_collect(root, SMPLX_NAMES))
            smpl_found.update(_collect(root, SMPL_NAMES, SMPL_ALIASES))

        if args.j14:
            j14 = Path(args.j14)
            if j14.is_file():
                smplx_found.setdefault("SMPLX_to_J14.pkl", j14)

        copied = _copy(smplx_found, smplx_dir) + _copy(smpl_found, smpl_dir)
        for path in copied:
            print("COPIED", path)
        missing = [n for n in SMPLX_NAMES if n not in smplx_found] + [n for n in SMPL_NAMES if n not in smpl_found]
        if missing:
            print("MISSING", ", ".join(missing), file=sys.stderr)
            return 1
        print("SMPL ASSETS READY", models_dir)
        return 0
    finally:
        for tmp in temp_dirs:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

"""Pose2Rig worker: newline-delimited JSON over stdio.

No bpy imports.  The Blender extension starts this process (or a dedicated
Python environment) and exchanges one JSON object per line.  The worker also
runs when the extension is installed under a different package name
(bl_ext.user_default.pose2rig), so imports are resolved dynamically.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import traceback
from pathlib import Path

# Package directory (pose2rig_blender in source, pose2rig in an installed extension).
_PACKAGE_DIR = Path(__file__).resolve().parents[1]
_PACKAGE_NAME = _PACKAGE_DIR.name
_PARENT_DIR = str(_PACKAGE_DIR.parent)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

_schema = importlib.import_module(f"{_PACKAGE_NAME}.core.schema")
_base = importlib.import_module(f"{_PACKAGE_NAME}.worker.engines.base")
_registry = importlib.import_module(f"{_PACKAGE_NAME}.worker.engines.registry")

PoseSchemaError = _schema.PoseSchemaError
validate_pose = _schema.validate_pose
EngineError = _base.EngineError
EngineUnavailable = _base.EngineUnavailable
get_engine = _registry.get_engine

PROTOCOL = "pose2rig/1"
ENGINES = ["mock", "smplerx"]


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _log(message: str) -> None:
    sys.stderr.write(message.rstrip() + "\n")
    sys.stderr.flush()


def _error(request_id, code, message, details=None):
    return {
        "type": "error",
        "request_id": request_id,
        "error": {"code": code, "message": message, "details": details or []},
    }


def handle(request: dict, default_engine: str, model_dir: str | None, fixture: str | None) -> dict | None:
    request_id = request.get("request_id")
    kind = request.get("type")
    if kind == "hello":
        return {
            "type": "hello",
            "protocol": PROTOCOL,
            "engines": ENGINES,
            "python": sys.version.split()[0],
            "pid": os.getpid(),
        }
    if kind == "ping":
        return {"type": "pong", "request_id": request_id}
    if kind == "shutdown":
        return {"type": "bye", "request_id": request_id}
    if kind != "infer":
        return _error(request_id, "BAD_REQUEST", f"unknown message type: {kind!r}")

    image_path = request.get("image_path")
    if not isinstance(image_path, str) or not image_path:
        return _error(request_id, "BAD_REQUEST", "image_path is required")
    engine_name = request.get("engine") or default_engine
    options = dict(request.get("options") or {})
    options["request_id"] = request_id
    config = {
        "model_dir": options.get("model_dir") or model_dir,
        "fixture_path": fixture,
        "device": options.get("device", "cuda"),
        "variant": options.get("variant", "s32"),
        "repo_dir": options.get("repo_dir") or None,
    }
    try:
        engine = get_engine(engine_name, config)
        pose = engine.infer(image_path, options)
        pose["request_id"] = str(request_id or pose.get("request_id") or "unknown")
        pose = validate_pose(pose)
        return {"type": "result", "request_id": request_id, "pose": pose}
    except EngineUnavailable as exc:
        return _error(request_id, "ENGINE_UNAVAILABLE", str(exc))
    except EngineError as exc:
        return _error(request_id, "ENGINE_ERROR", str(exc))
    except PoseSchemaError as exc:
        return _error(request_id, "SCHEMA_ERROR", "pose result failed validation", exc.errors)
    except Exception as exc:  # noqa: BLE001
        _log(traceback.format_exc())
        return _error(request_id, "INTERNAL_ERROR", f"{type(exc).__name__}: {exc}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", default="mock", choices=ENGINES)
    parser.add_argument("--model-dir", default=None)
    parser.add_argument("--fixture", default=None)
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    _log(f"pose2rig worker ready: protocol={PROTOCOL} default_engine={args.engine} pid={os.getpid()}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _send(_error(None, "BAD_JSON", f"invalid JSON: {exc}"))
            continue
        if not isinstance(request, dict):
            _send(_error(None, "BAD_JSON", "request must be an object"))
            continue
        response = handle(request, args.engine, args.model_dir, args.fixture)
        if response is not None:
            _send(response)
        if request.get("type") == "shutdown":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

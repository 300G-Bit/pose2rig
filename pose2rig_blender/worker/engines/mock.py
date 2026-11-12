"""Deterministic mock engine used to exercise the full plugin pipeline."""

from __future__ import annotations

import copy
import json
import os
import struct
from pathlib import Path

from .base import Engine, EngineError


def _png_size(data: bytes):
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    return None


def _jpeg_size(data: bytes):
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in (0xD8, 0xD9):
            continue
        if i + 2 > len(data):
            break
        length = struct.unpack(">H", data[i:i + 2])[0]
        if length < 2:
            break
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 7 <= len(data):
                h, w = struct.unpack(">HH", data[i + 3:i + 7])
                return w, h
        i += length
    return None


def image_size(path: str):
    try:
        with open(path, "rb") as handle:
            data = handle.read(64 * 1024)
    except OSError:
        return None
    return _png_size(data) or _jpeg_size(data)


class MockEngine(Engine):
    id = "mock"

    def __init__(self, fixture_path: str | None = None):
        if fixture_path is None:
            fixture_path = Path(__file__).resolve().parents[2] / "assets" / "fixtures" / "mock_pose.json"
        self.fixture_path = str(fixture_path)

    def infer(self, image_path: str, options: dict) -> dict:
        if not os.path.isfile(image_path):
            raise EngineError(f"image not found: {image_path}")
        with open(self.fixture_path, "r", encoding="utf-8") as handle:
            pose = json.load(handle)
        pose = copy.deepcopy(pose)
        size = image_size(image_path)
        if size:
            pose["image"]["width"], pose["image"]["height"] = int(size[0]), int(size[1])
        elif options.get("image_width") and options.get("image_height"):
            pose["image"]["width"] = int(options["image_width"])
            pose["image"]["height"] = int(options["image_height"])
        pose["request_id"] = str(options.get("request_id") or "mock-request")
        pose["engine"]["runtime"] = "mock"
        pose["diagnostics"]["warnings"] = ["mock fixture, not a real inference"]
        return pose

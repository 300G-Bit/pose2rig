"""Engine factory."""

from __future__ import annotations

from .mock import MockEngine
from .smplerx import SmplerXEngine


def get_engine(name: str, config: dict | None = None):
    config = config or {}
    if name == "mock":
        return MockEngine(config.get("fixture_path"))
    if name == "smplerx":
        return SmplerXEngine(
            config.get("model_dir"),
            config.get("device", "cuda"),
            config.get("variant", "s32"),
            config.get("repo_dir") or None,
        )
    raise ValueError(f"unknown engine: {name}")

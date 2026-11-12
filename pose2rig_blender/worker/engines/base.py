"""Engine interface for the Pose2Rig worker."""

from __future__ import annotations


class EngineError(RuntimeError):
    """Engine failed in a recoverable way."""


class EngineUnavailable(EngineError):
    """Engine is not configured (missing weights, package, or device)."""


class Engine:
    id = "base"

    def infer(self, image_path: str, options: dict) -> dict:
        raise NotImplementedError

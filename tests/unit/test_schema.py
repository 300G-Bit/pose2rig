import copy
import json
import unittest
from pathlib import Path

import numpy as np

from pose2rig_blender.core.schema import PoseSchemaError, validate_pose

FIXTURE = Path(__file__).resolve().parents[2] / "pose2rig_blender" / "assets" / "fixtures" / "mock_pose.json"


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class SchemaTests(unittest.TestCase):
    def test_fixture_is_valid(self):
        pose = validate_pose(fixture())
        self.assertEqual(pose["schema_version"], "pose_result/v1")
        self.assertEqual(len(pose["source_skeleton"]["joint_names"]), len(pose["local_pose_rotations"]))
        self.assertIsInstance(pose["image"]["width"], int)

    def test_missing_field_rejected(self):
        data = fixture()
        del data["camera"]
        with self.assertRaises(PoseSchemaError):
            validate_pose(data)

    def test_non_orthonormal_rejected(self):
        data = fixture()
        data["local_pose_rotations"][0] = [[1, 0.5, 0], [0, 1, 0], [0, 0, 1]]
        with self.assertRaises(PoseSchemaError):
            validate_pose(data)

    def test_parent_must_point_earlier(self):
        data = fixture()
        data["source_skeleton"]["parents"][1] = 5
        with self.assertRaises(PoseSchemaError):
            validate_pose(data)

    def test_length_mismatch_rejected(self):
        data = fixture()
        data["local_pose_rotations"].pop()
        with self.assertRaises(PoseSchemaError):
            validate_pose(data)

    def test_nan_rejected(self):
        data = fixture()
        data["local_pose_rotations"][0] = [[float("nan"), 0, 0], [0, 1, 0], [0, 0, 1]]
        with self.assertRaises(PoseSchemaError):
            validate_pose(data)

    def test_bad_sensor_fit_rejected(self):
        data = fixture()
        data["camera"]["sensor_fit"] = "DIAGONAL"
        with self.assertRaises(PoseSchemaError):
            validate_pose(data)


if __name__ == "__main__":
    unittest.main()

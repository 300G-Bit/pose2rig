import unittest

import numpy as np

from pose2rig_blender.core.schema import validate_pose
from pose2rig_blender.worker.engines.model_layout import check_layout
from pose2rig_blender.worker.engines.smplerx import SmplerXEngine, prediction_to_pose


class SmplerXAdapterTests(unittest.TestCase):
    def test_prediction_converts_to_valid_canonical_pose(self):
        pred = {
            "smplx_root_pose": [0.1, 0.0, 0.0],
            "smplx_body_pose": np.zeros((21, 3)).tolist(),
            "smplx_lhand_pose": np.zeros((15, 3)).tolist(),
            "smplx_rhand_pose": np.zeros((15, 3)).tolist(),
            "smplx_jaw_pose": [0.0, 0.0, 0.0],
            "cam_trans": [0.0, 0.0, 3.0],
            "focal": [2000.0, 2000.0],
            "princpt": [600.0, 800.0],
        }
        pred["smplx_lhand_pose"][0] = [0.2, 0.0, 0.0]
        pose = prediction_to_pose(pred, 1200, 1600, bbox_xyxy=[300, 200, 900, 1400])
        checked = validate_pose(pose)
        self.assertEqual(len(checked["source_skeleton"]["joint_names"]), 55)
        self.assertEqual(len(checked["local_pose_rotations"]), 55)
        self.assertAlmostEqual(checked["camera"]["fx_px"], 2000.0)
        self.assertFalse(np.allclose(checked["local_pose_rotations"][25], np.eye(3)))

    def test_fingers_can_be_disabled(self):
        pred = {
            "smplx_root_pose": [0, 0, 0],
            "smplx_body_pose": np.zeros((21, 3)).tolist(),
            "smplx_lhand_pose": np.ones((15, 3)).tolist(),
            "smplx_rhand_pose": np.ones((15, 3)).tolist(),
            "focal": [1500.0, 1500.0],
            "princpt": [600.0, 800.0],
        }
        pose = prediction_to_pose(pred, 1200, 1600, include_fingers=False)
        for index in range(25, 55):
            np.testing.assert_allclose(pose["local_pose_rotations"][index], np.eye(3), atol=1e-9)

    def test_virtual_focal_scales_with_bbox(self):
        pred = {"smplx_root_pose": [0, 0, 0], "smplx_body_pose": np.zeros((21, 3)).tolist()}
        pose = prediction_to_pose(pred, 1000, 1000, bbox_xyxy=[100, 100, 400, 700])
        self.assertAlmostEqual(pose["camera"]["fx_px"], 5000.0 / 256.0 * 300.0)
        self.assertAlmostEqual(pose["camera"]["cx_px"], 250.0)

    def test_layout_reports_missing(self):
        layout = check_layout("", "s32")
        self.assertFalse(layout["ready"])
        self.assertTrue(layout["missing"])

    def test_engine_probe_without_model_dir(self):
        engine = SmplerXEngine("", "cuda", "s32")
        self.assertFalse(engine.probe()["ready"])


if __name__ == "__main__":
    unittest.main()

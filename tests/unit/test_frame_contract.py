import math
import unittest

import numpy as np

from pose2rig_blender.core import retarget_math
from pose2rig_blender.worker.engines.smplerx import REST_CAM, prediction_to_pose


class FrameContractTests(unittest.TestCase):
    def test_smplx_adapter_declares_rest_frame(self):
        pred = {
            "smplx_root_pose": [math.pi, 0.0, 0.0],
            "smplx_body_pose": np.zeros((21, 3)).tolist(),
            "smplx_lhand_pose": np.zeros((15, 3)).tolist(),
            "smplx_rhand_pose": np.zeros((15, 3)).tolist(),
            "smplx_jaw_pose": [0.0, 0.0, 0.0],
            "cam_trans": [0.0, 0.0, 3.0],
            "focal": [2000.0, 2000.0],
            "princpt": [500.0, 500.0],
        }
        pose = prediction_to_pose(pred, 1000, 1000, bbox_xyxy=[100, 100, 400, 700])
        self.assertEqual(pose["conventions"]["skeleton_frame"], "camera")
        np.testing.assert_allclose(pose["source_skeleton"]["rest_rotations"][0], REST_CAM, atol=1e-9)
        np.testing.assert_allclose(pose["local_pose_rotations"][0], np.eye(3), atol=1e-9)
        self.assertIn("input_quality", pose)

    def test_camera_to_blender_basis_cancels_rest_orientation(self):
        # A standing SMPL-X T-pose has global_orient = REST_CAM.  Stored as a
        # root local rotation relative to the declared rest, it is identity.
        local_root = REST_CAM.T @ REST_CAM
        basis, _ = retarget_math.compute_target_basis(
            [REST_CAM.tolist()],
            [-1],
            [local_root.tolist()],
            [np.eye(3).tolist()],
            [-1],
            {0: 0},
            world_from_source=[[1, 0, 0], [0, 0, 1], [0, -1, 0]],
        )
        np.testing.assert_allclose(basis[0], np.eye(3), atol=1e-9)


if __name__ == "__main__":
    unittest.main()
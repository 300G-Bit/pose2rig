import math
import unittest

import numpy as np

from pose2rig_blender.core import retarget_math as rm


def rot_x(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)


def rot_y(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)


def rot_z(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


class RetargetMathTests(unittest.TestCase):
    def test_identity_pose_returns_identity_basis(self):
        rest = [np.eye(3), rot_x(20), rot_y(-10)]
        parents = [-1, 0, 1]
        local = [np.eye(3)] * 3
        basis, _ = rm.compute_target_basis(rest, parents, local, rest, parents, {0: 0, 1: 1, 2: 2})
        for m in basis:
            np.testing.assert_allclose(m, np.eye(3), atol=1e-9)

    def test_single_bone_matches_source_local_when_rest_identity(self):
        rest = [np.eye(3)]
        parents = [-1]
        local = [rot_z(37)]
        basis, _ = rm.compute_target_basis(rest, parents, local, rest, parents, {0: 0})
        np.testing.assert_allclose(basis[0], rot_z(37), atol=1e-9)

    def test_parent_chain_propagates(self):
        rest = [np.eye(3)] * 3
        parents = [-1, 0, 1]
        local = [rot_y(30), rot_x(15), rot_z(-20)]
        basis, _ = rm.compute_target_basis(rest, parents, local, rest, parents, {0: 0, 1: 1, 2: 2})
        np.testing.assert_allclose(basis[0], local[0], atol=1e-9)
        np.testing.assert_allclose(basis[1], local[1], atol=1e-9)
        np.testing.assert_allclose(basis[2], local[2], atol=1e-9)

    def test_rest_offset_is_cancelled(self):
        source_rest = [np.eye(3), rot_x(90)]
        target_rest = [np.eye(3), rot_z(-45)]
        parents = [-1, 0]
        local = [np.eye(3), np.eye(3)]
        basis, _ = rm.compute_target_basis(source_rest, parents, local, target_rest, parents, {0: 0, 1: 1})
        for m in basis:
            np.testing.assert_allclose(m, np.eye(3), atol=1e-9)

    def test_unmapped_bone_keeps_rest(self):
        source_rest = [np.eye(3), np.eye(3)]
        target_rest = [np.eye(3), rot_y(25)]
        parents = [-1, 0]
        local = [rot_z(10), rot_z(20)]
        basis, _ = rm.compute_target_basis(source_rest, parents, local, target_rest, parents, {0: 0})
        np.testing.assert_allclose(basis[1], np.eye(3), atol=1e-9)

    def test_orthonormalize_repairs_small_noise(self):
        m = np.eye(3) + np.array([[0, 0.01, 0], [0, 0, 0.01], [0, 0, 0]])
        fixed = rm.orthonormalize(m)
        np.testing.assert_allclose(fixed.T @ fixed, np.eye(3), atol=1e-9)
        self.assertGreater(np.linalg.det(fixed), 0)

    def test_rotation_between_maps_vectors(self):
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        r = rm.rotation_between(a, b)
        np.testing.assert_allclose(r @ a, b, atol=1e-9)
        np.testing.assert_allclose(r.T @ r, np.eye(3), atol=1e-9)

    def test_invalid_skeleton_detected(self):
        with self.assertRaises(rm.RetargetMathError):
            rm.validate_skeleton(["a", "b"], [-1, 5])


if __name__ == "__main__":
    unittest.main()

"""Blender-side retarget adapter.

Reads rest data from a target armature, computes local pose basis matrices
with the pure-math module, and writes quaternions to pose bones.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from . import retarget_math


class RetargetError(RuntimeError):
    pass


ASSETS = Path(__file__).resolve().parent.parent / "assets" / "presets"


def _topological_bones(armature):
    bones = list(armature.data.bones)
    by_name = {b.name: b for b in bones}
    ordered = []
    remaining = list(bones)
    guard = 0
    while remaining and guard < len(bones) + 5:
        guard += 1
        progressed = False
        for bone in list(remaining):
            if bone.parent is None or bone.parent.name in {b.name for b in ordered}:
                ordered.append(bone)
                remaining.remove(bone)
                progressed = True
        if not progressed:
            break
    if remaining:
        ordered.extend(remaining)
    return ordered


def load_preset(name: str) -> dict:
    path = ASSETS / f"{name}.json"
    if not path.is_file():
        raise RetargetError(f"preset not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _preset_hits(armature, preset_name):
    preset = load_preset(preset_name)
    names = {b.name for b in armature.data.bones}
    prefixes = preset.get("prefixes", [""])
    required = preset.get("required_joints") or list(preset.get("bone_mapping", {}).keys())
    hits = 0
    for joint in required:
        if _find_bone(names, preset.get("bone_mapping", {}).get(joint, []), prefixes):
            hits += 1
    return hits, len(required)


def detect_preset(armature) -> str:
    """Pick the preset with the highest required-joint coverage.

    Candidate names may be lower-case VRM, MMD Tools `.L/.R` suffixes or
    Mixamo prefixes; scoring avoids brittle prefix-only detection.
    """
    best_name = None
    best_score = (0, 0)
    for name in ("mixamo", "vrm", "mmd"):
        try:
            hits, total = _preset_hits(armature, name)
        except RetargetError:
            continue
        if total and hits >= max(1, int(math.ceil(total * 0.6))):
            if hits > best_score[0] or (hits == best_score[0] and total > best_score[1]):
                best_name, best_score = name, (hits, total)
    if best_name:
        return best_name
    raise RetargetError("cannot auto-detect rig; choose Mixamo, VRM or MMD preset")


def _find_bone(target_names, candidates, prefixes):
    for prefix in prefixes:
        for candidate in candidates:
            name = prefix + candidate
            if name in target_names:
                return name
    return None


def build_mapping(armature, pose: dict, preset_name: str, exclude_joints=None) -> dict:
    if preset_name == "AUTO":
        preset_name = detect_preset(armature)
    preset = load_preset(preset_name)
    prefixes = preset.get("prefixes", [""])
    target_names = {b.name for b in armature.data.bones}
    source_names = pose["source_skeleton"]["joint_names"]
    source_index = {name: i for i, name in enumerate(source_names)}
    bone_to_target_index = {b.name: i for i, b in enumerate(_topological_bones(armature))}
    exclude = set(exclude_joints or ())

    mapping = {}
    missing = []
    for source_joint, candidates in preset["bone_mapping"].items():
        if source_joint not in source_index or source_joint in exclude:
            continue
        bone_name = _find_bone(target_names, candidates, prefixes)
        if bone_name is None:
            if source_joint in preset.get("required_joints", []) and source_joint not in exclude:
                missing.append(source_joint)
            continue
        mapping[bone_to_target_index[bone_name]] = source_index[source_joint]
    if missing:
        raise RetargetError("target rig is missing required joints: " + ", ".join(missing))
    return {
        "preset": preset,
        "preset_name": preset_name,
        "mapping": mapping,
        "bone_order": _topological_bones(armature),
    }


def _rest_arrays(armature, bone_order):
    bone_to_index = {b.name: i for i, b in enumerate(bone_order)}
    rest = []
    parents = []
    for bone in bone_order:
        m = bone.matrix_local.to_3x3()
        rest.append(retarget_math.orthonormalize([[m[r][c] for c in range(3)] for r in range(3)]))
        parents.append(bone_to_index[bone.parent.name] if bone.parent else -1)
    return rest, parents


def _leg_length_from_points(hip, knee, ankle):
    return float((knee - hip).length + (ankle - knee).length)


def _source_leg_length(pose):
    names = pose["source_skeleton"]["joint_names"]
    positions = pose["source_skeleton"]["rest_positions"]
    idx = {n: i for i, n in enumerate(names)}
    try:
        left = _leg_length_from_points(
            Vector(positions[idx["left_hip"]]),
            Vector(positions[idx["left_knee"]]),
            Vector(positions[idx["left_ankle"]]),
        )
        right = _leg_length_from_points(
            Vector(positions[idx["right_hip"]]),
            Vector(positions[idx["right_knee"]]),
            Vector(positions[idx["right_ankle"]]),
        )
        return (left + right) * 0.5
    except KeyError:
        return 0.0


def _target_leg_length(armature, preset):
    mapping = preset["bone_mapping"]
    names = [b.name for b in armature.data.bones]

    def find(joint):
        for candidate in mapping.get(joint, []):
            for prefix in preset.get("prefixes", [""]):
                if prefix + candidate in names:
                    return armature.data.bones[prefix + candidate]
        return None

    hip, knee, ankle = find("left_hip"), find("left_knee"), find("left_ankle")
    if not (hip and knee and ankle):
        return 0.0
    return _leg_length_from_points(hip.head_local, knee.head_local, ankle.head_local)


def _frame_basis(pose):
    """Return the source-frame -> Blender-world rotation, or None for world."""
    conventions = pose.get("conventions") or {}
    explicit = conventions.get("world_from_source")
    if explicit is not None:
        return retarget_math.as_mat3(explicit, "conventions.world_from_source")
    if conventions.get("skeleton_frame", "world") == "camera":
        # OpenCV camera axes: x right, y down, z forward -> Blender Z-up.
        return retarget_math.as_mat3([[1, 0, 0], [0, 0, 1], [0, -1, 0]], "camera_to_blender")
    return None


def _object_rotation(armature):
    q = armature.matrix_world.to_quaternion()
    m = q.to_matrix()
    return retarget_math.as_mat3([[m[r][c] for c in range(3)] for r in range(3)], "armature.matrix_world")


def _mute_ik_constraints(armature):
    """Mute IK constraints while applying a full FK pose.

    MMD/VRM rigs often carry IK constraints on legs.  Setting deform-bone
    rotations while IK is active makes the solver re-bend knees to hold the
    old IK targets, which destroys the source pose.  The original mute states
    are returned for Cancel/Reset restoration.
    """
    states = []
    for pb in armature.pose.bones:
        for constraint in pb.constraints:
            if constraint.type == "IK":
                states.append((pb.name, constraint.name, bool(constraint.mute)))
                constraint.mute = True
    return states


def _rest_direction_alignments(armature, pose, info, frame_basis, object_rotation):
    """Build A_b rotations aligning target rest bone directions to source rest directions.

    This is the semantic/rest-pose alignment that makes A-pose MMD arms behave
    like T-pose SMPL-X arms.  Without it, a world-space delta applied to an
    A-pose arm rotates the already-lowered arm instead of lifting it to the
    source direction.
    """
    skel = pose["source_skeleton"]
    rest_pos = np.asarray(skel["rest_positions"], dtype=np.float64)
    parents = [int(p) for p in skel["parents"]]
    rest_rots = skel["rest_rotations"]
    names = skel["joint_names"]
    # Legs already share a near-vertical rest direction with MMD; applying A_b
    # there would rotate the legs outward and hurt the correct leg pose.  Neck
    # and head are left on the source pose because their rest difference is small.
    skip_joints = {
        "left_hip", "right_hip", "left_knee", "right_knee",
        "left_ankle", "right_ankle", "left_foot", "right_foot",
        "neck", "head",
    }
    children = {}
    for i, parent in enumerate(parents):
        children.setdefault(parent, []).append(i)
    preferred_child = {
        "left_wrist": "left_middle1",
        "right_wrist": "right_middle1",
    }
    out = {}
    for target_index, source_index in info["mapping"].items():
        parent = parents[source_index]
        if parent < 0 or names[source_index] in skip_joints:
            continue
        bone = info["bone_order"][target_index]
        target_vec = np.array([
            float(bone.tail_local[i] - bone.head_local[i]) for i in range(3)
        ], dtype=np.float64)
        if np.linalg.norm(target_vec) < 1e-9:
            continue
        # A bone points from this joint toward its child.  Using the parent
        # offset here would compare the wrong rest segment (e.g. collar->shoulder
        # instead of shoulder->elbow).  Leaf bones fall back to their parent.
        child_name = preferred_child.get(names[source_index])
        child_index = None
        if child_name and child_name in names:
            child_index = names.index(child_name)
        elif children.get(source_index) and names[source_index] != "head":
            child_index = children[source_index][0]
        if child_index is not None:
            rest_rot = np.asarray(rest_rots[source_index], dtype=np.float64)
            source_vec = rest_rot @ (rest_pos[child_index] - rest_pos[source_index])
        else:
            parent_rest = np.asarray(rest_rots[parent], dtype=np.float64)
            source_vec = parent_rest @ (rest_pos[source_index] - rest_pos[parent])
        if frame_basis is not None:
            source_vec = frame_basis @ source_vec
        source_vec = object_rotation.T @ source_vec
        denom = np.linalg.norm(target_vec) * np.linalg.norm(source_vec)
        if denom < 1e-9:
            continue
        cos_angle = float(np.clip(np.dot(target_vec, source_vec) / denom, -1.0, 1.0))
        # Only correct material rest-direction differences (A/T-pose arms);
        # small differences are bone-roll noise and would over-rotate the pose.
        if math.acos(cos_angle) < math.radians(0.5):
            continue
        out[target_index] = retarget_math.rotation_between(target_vec, source_vec)
    return out


def apply_pose(armature, pose: dict, preset_name: str = "AUTO", options: dict | None = None) -> dict:
    options = options or {}
    mode = options.get("mapping_mode", "AUTO")
    quality = pose.get("input_quality") or {}
    exclude_joints = set()
    if mode == "UPPER_BODY" or (mode == "AUTO" and quality.get("lower_body_visible") is False):
        exclude_joints = {
            "left_hip", "right_hip", "left_knee", "right_knee",
            "left_ankle", "right_ankle", "left_foot", "right_foot",
        }
    info = build_mapping(armature, pose, preset_name, exclude_joints=exclude_joints)
    bone_order = info["bone_order"]
    target_rest, target_parents = _rest_arrays(armature, bone_order)
    frame_basis = _frame_basis(pose)
    object_rotation = _object_rotation(armature)
    alignments = _rest_direction_alignments(armature, pose, info, frame_basis, object_rotation)
    basis, world = retarget_math.compute_target_basis(
        pose["source_skeleton"]["rest_rotations"],
        pose["source_skeleton"]["parents"],
        pose["local_pose_rotations"],
        target_rest,
        target_parents,
        info["mapping"],
        world_from_source=frame_basis,
        target_object_rotation=object_rotation,
        alignments=alignments,
    )

    if armature.mode != "POSE":
        bpy.context.view_layer.objects.active = armature
        armature.select_set(True)
        bpy.ops.object.mode_set(mode="POSE")

    # IK muting was intentionally not enabled by default: it makes MMD feet
    # lose their tiptoe/foot orientation.  Keep the rig constraints intact;
    # callers that explicitly want FK-only legs can pass mute_ik=True.
    muted_ik = _mute_ik_constraints(armature) if options.get("mute_ik", False) else []

    for i, bone in enumerate(bone_order):
        pb = armature.pose.bones.get(bone.name)
        if pb is None:
            continue
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Matrix(basis[i]).to_quaternion()

    # Root translation: scale by leg ratio, then convert source-world to
    # target armature space and to the root bone's local space.
    root_name = info["preset"].get("root")
    root_pb = None
    for bone in bone_order:
        if bone.name == root_name or (root_name is None and bone.parent is None):
            root_pb = armature.pose.bones.get(bone.name)
            break
    if root_pb is not None:
        src_len = _source_leg_length(pose)
        tgt_len = _target_leg_length(armature, info["preset"])
        translation = retarget_math.scale_root_translation(pose.get("root_translation", [0, 0, 0]), src_len, tgt_len)
        if frame_basis is not None:
            translation = frame_basis @ translation
        translation = object_rotation.T @ translation
        local = root_pb.bone.matrix_local.to_3x3().inverted() @ Vector(tuple(float(v) for v in translation))
        root_pb.location = local

    bpy.context.view_layer.update()

    if options.get("shoulder_relax", 0.0) > 0:
        from .pose_modifiers import apply_shoulder_relax
        apply_shoulder_relax(armature, info, options["shoulder_relax"])
    if options.get("spine_influence", 1.0) != 1.0:
        from .pose_modifiers import apply_spine_influence
        apply_spine_influence(armature, info, options["spine_influence"])
    if options.get("ground_snap", False):
        from .pose_modifiers import snap_to_ground
        snap_to_ground(armature, info)

    bpy.context.view_layer.update()
    return {"mapped_bones": len(info["mapping"]), "preset": info["preset_name"], "muted_ik": muted_ik}


def clear_pose(armature):
    if armature.mode != "POSE":
        bpy.context.view_layer.objects.active = armature
        armature.select_set(True)
        bpy.ops.object.mode_set(mode="POSE")
    for pb in armature.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion((1, 0, 0, 0))
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()

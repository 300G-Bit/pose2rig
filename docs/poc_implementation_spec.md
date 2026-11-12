# Pose2Rig PoC 实现规范（v1）

本文件把 `poc_design.md` 的设计落成可执行的接口、协议和验收标准。代码以本文件为准；实现变更先改本文件。

## 1. 模块 API

### 1.1 纯数学层 `core/retarget_math.py`

```python
as_mat3(value, name="matrix") -> np.ndarray            # 校验 3x3，返回 float64
orthonormalize(matrix) -> np.ndarray                    # SVD 最近正交旋转
validate_rotation(matrix, name="matrix", atol=1e-3) -> np.ndarray
validate_skeleton(joint_names, parents) -> list[int]    # root=-1，parent < i
rest_relative(rest_rotations, parents) -> list[np.ndarray]
source_world(rest_rotations, parents, local_pose_rotations) -> list[np.ndarray]
world_deltas(pose_world, rest_world) -> list[np.ndarray]
target_world(deltas, source_map, target_rest, target_parents) -> tuple[list, list]
local_basis(target_world_rotations, rel, parents) -> list[np.ndarray]
compute_target_basis(source_rest, source_parents, source_local_pose,
                     target_rest, target_parents, source_map)
    -> tuple[list[np.ndarray], list[np.ndarray]]
scale_root_translation(translation, source_leg_length, target_leg_length) -> np.ndarray
```

失败统一抛 `RetargetMathError`，不返回 NaN/None。

### 1.2 数据契约 `core/schema.py`

```python
validate_pose(data: dict) -> dict       # 返回规范化副本
load_pose(path: str) -> dict            # 读文件并校验
```

失败抛 `PoseSchemaError`，`.errors` 为字符串列表。所有 3x3 旋转矩阵检查正交性与行列式；`model_to_camera` 只检查 4x4、有限、左上 3x3 正交、最后一行 `[0,0,0,1]`。

### 1.3 Blender 重定向 `core/blender_retarget.py`

```python
load_preset(name: str) -> dict                  # name in {"mixamo","vrm","mmd"}
detect_preset(armature) -> str                  # "mixamo" / "vrm"，失败抛 RetargetError
build_mapping(armature, pose, preset_name) -> dict
apply_pose(armature, pose, preset_name="AUTO", options=None) -> dict
clear_pose(armature) -> None
```

`options` 键：`shoulder_relax` (0..1)、`spine_influence` (0.5..1.5)、`ground_snap` (bool)。
返回 `{"mapped_bones": int, "preset": str}`。

### 1.4 相机 `core/camera_builder.py`

```python
_lens_mm(fx_px, width, height, sensor_width_mm, sensor_fit) -> float
_camera_pose_from_model_to_camera(m) -> tuple[Vector, Matrix]
create_or_update_camera(scene, pose, image_path=None, opacity=0.5,
                        name="Pose2Rig_Camera", match_resolution=True) -> Object
project_point(scene, camera_obj, point) -> Vector
delete_camera(scene, name="Pose2Rig_Camera") -> None
```

`match_resolution=True` 时把 `scene.render.resolution_x/y` 设为图片尺寸，保证 `world_to_camera_view` 与参考图同宽高比。

### 1.5 UI/Operator

| Operator | idname | 作用 |
|---|---|---|
| Generate | `pose2rig.generate` | 校验输入，启动 Worker，定时器轮询 |
| Apply | `pose2rig.apply` | 清理预览快照并 `undo_push` |
| Cancel | `pose2rig.cancel` | 恢复到本代 Generate 前的快照 |
| Reset | `pose2rig.reset` | 清空姿态、相机和最后结果 |
| Save Pose | `pose2rig.save_pose` | 写 `pose_result/v1` JSON |
| Load Pose | `pose2rig.load_pose` | 读 JSON 并应用 |
| Check Engine | `pose2rig.probe_engine` | 检查 SMPLer-X 模型布局 |

属性组 `Scene.pose2rig`：`image_path`、`target_armature`、`preset`、`engine`、`include_fingers`、`auto_camera`、`show_reference`、`opacity`、`shoulder_relax`、`spine_influence`、`ground_snap`、`status`、`last_pose_json`。

### 1.6 SMPLer-X 适配层 `worker/engines/smplerx.py`

```python
SmplerXEngine(model_dir, device="cuda", variant="s32", repo_dir=None)
probe() -> dict                         # model_layout.check_layout
infer(image_path, options) -> dict      # 调 reference inference.py，再转 CanonicalPose
prediction_to_pose(prediction, image_width, image_height,
                   bbox_xyxy=None, include_fingers=True, engine_meta=None) -> dict
```

`options.repo_dir` 指向 SMPLer-X 源码；`options.model_dir` 指向模型目录。

## 2. Worker IPC

传输：stdin/stdout 每行一个 JSON；stderr 只写日志。stdout 不得输出非协议文本。

| type | 方向 | 字段 | 响应 |
|---|---|---|---|
| `hello` | Blender→Worker | — | `{type:"hello", protocol:"pose2rig/1", engines:["mock","smplerx"], python, pid}` |
| `ping` | Blender→Worker | `request_id` | `{type:"pong", request_id}` |
| `infer` | Blender→Worker | `request_id, engine, image_path, options` | `result` 或 `error` |
| `shutdown` | Blender→Worker | — | `{type:"bye"}` |

`infer.options`：`image_width`、`image_height`、`include_fingers`、`model_dir`、`repo_dir`、`variant`、`device`、`bbox_xyxy`（可选）。

错误响应：

```json
{"type":"error","request_id":"...","error":{"code":"ENGINE_UNAVAILABLE","message":"...","details":["..."]}}
```

错误码：`BAD_JSON`、`BAD_REQUEST`、`ENGINE_UNAVAILABLE`、`ENGINE_ERROR`、`SCHEMA_ERROR`、`INTERNAL_ERROR`、`CLIENT_ERROR`、`CANCELLED`、`TIMEOUT`。

超时：客户端默认 180 s；超时后 terminate 进程树。取消：先 terminate，再丢弃迟到结果；Blender 侧 `generation` 递增，旧结果不应用。

## 3. 预览/应用/取消

- Generate 前：`_STATE["snapshot"] = snapshot_pose(armature)`，记录所有 pose bone 的 rotation_mode/quaternion/location/scale。
- Generate 结果：只写 pose 通道，不修改 rest pose、不 `transform_apply`。
- Apply：`bpy.ops.ed.undo_push(message="Pose2Rig Apply")`，清空 snapshot。
- Cancel：`restore_pose(armature, snapshot)`，清空 snapshot。
- Reset：`clear_pose` + 删除相机 + 清空 last_pose_json。
- 滑块：从 `last_pose_json` 的不可变 base 重新应用，不累积。

## 4. 预设格式

```json
{
  "preset_name": "Mixamo",
  "prefixes": ["mixamorig:", ""],
  "bone_mapping": {"pelvis": ["Hips"], "...": ["..."]},
  "required_joints": ["pelvis", "spine1", "..."],
  "root": "Hips"
}
```

- `bone_mapping`：源 SMPL-X 关节名 → 目标骨候选名列表，按顺序取第一个存在者。MMD 预设同时包含日文骨名与 `.L/.R` 后缀形式（手指数字为全角）。
- `required_joints`：缺失即 `RetargetError`，不允许静默跳过。
- `prefixes`：Mixamo 常见 `mixamorig:`；VRM 常见 `J_Bip_`。
- 自定义映射保存到 `bpy.utils.extension_path_user(__package__, "mappings")`（后续里程碑）。

## 5. Worker 环境与模型布局

- Mock：Blender 自带 Python（Windows 为 `<blender>/<version>/python/bin/python.exe`），只依赖 numpy。
- SMPLer-X：独立 venv；Codex 通过 `worker_python` 偏好指定；不要装进 Blender Python。
- 模型目录结构见 `worker/engines/model_layout.py` 的 `required_files()`。
- `probe_engine` 只检查文件存在性，不导入 torch。

## 6. 测试矩阵

| 测试 | 文件 | 断言 |
|---|---|---|
| 数学 identity/父链/rest offset | `tests/unit/test_retarget_math.py` | 7 项全绿；误差 < 1e-9 |
| schema 校验 | `tests/unit/test_schema.py` | 7 项全绿；非法输入抛 PoseSchemaError |
| SMPLer-X 转换 | `tests/unit/test_smplerx_adapter.py` | 55 关节、focal、手指开关 |
| 相机 | `tests/blender_headless/test_core.py` | lens 45/60/45 mm；中心 (0.5,0.5)；主点 shift 误差 < 1e-4 |
| Mixamo 重定向 | `tests/blender_headless/test_core.py` | LeftHand 位移 > 0.05 m |
| VRM 重定向 | `tests/blender_headless/test_vrm.py` | J_Bip_L_Hand 位移 > 0.05 m |
| 手指 | `tests/blender_headless/test_hands.py` | 映射 52 骨；Index3 位移 > 0.005 m |
| 扩展注册/异步 | `tests/blender_headless/test_extension.py` | 注册/面板/Generate 到 Done |
| 滑块/Apply/Cancel/Reset | `tests/blender_headless/test_operators.py` | 滑块回 0 时 diff = 0；Cancel diff = 0 |
| 保存/加载 | `tests/blender_headless/test_save_load.py` | 往返 diff < 1e-4 |
| 脚底贴地 | `tests/blender_headless/test_ground.py` | 脚骨最低 tail z = 0 |
| 安装态扩展 | `tests/blender_headless/test_installed.py` | 从 ZIP 安装后 Generate 到 Done |

所有 Blender 测试使用 `--factory-startup`。

## 7. 已知限制（PoC）

- SMPLer-X 网络桥接尚未接真实权重；当前 `prediction_to_pose` 转换已可用。
- 多人策略未实现：第一版取主 bbox，多人时报告警告。
- 手部 PCA→旋转目前按 15×3 轴角处理；若权重用 PCA 需在 adapter 增加 PCA 解码。
- 主点 shift 已支持；EXIF 方向、镜头畸变未处理。
- 4.2/4.5 未测试；当前仅 5.2.2。

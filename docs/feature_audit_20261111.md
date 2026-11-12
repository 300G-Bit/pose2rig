# Pose2Rig 功能真实性审查记录

- 审查日期：2026-11-11
- 审查对象：`D:\blender5.2\pose_plugin`（Pose2Rig 0.1.0 PoC）
- 运行环境：Windows x64；Blender 5.2.2 LTS；SMPLer-X 独立环境 Python 3.8.20 / torch 1.12.0+cu113 / mmcv-full 1.7.1 / mmdet 2.26.0；RTX 3060 Laptop 6GB
- 审查方式：静态代码走查 + 19 个单元测试复跑 + 7 个 Blender headless 测试复跑 + 已安装扩展测试 + 真实 S32 单图推理 + MMD 499 骨真实模型应用与渲染 + 合成蒙皮网格数据完整性测试
- 证据目录：`docs/audit_evidence/`
- 后续问题分析：`audit_issue_analysis.md`

## 0. 结论摘要

**可以确认的功能**：扩展可构建、可安装、可启用；Mock 链路能跑通 UI/Worker/相机/姿态写入/Apply/Cancel/保存加载；`pose_result/v1` schema 能拒绝明显的坏矩阵和坏父链；真实 SMPLer-X S32 能在约 28–33 秒内产出 55 关节、合法 JSON；Mixamo 52 骨（22 身体 + 30 手指）、MMD 51 骨（21 身体 + 30 手指）的**名称映射**能建立；姿态写入不会修改网格顶点、边面、顶点组或修改器数据。

**核心问题**：真实 S32 的旋转数据是 **SMPL-X / 相机坐标语义**，插件没有做 `Y-up `→`Blender Z-up` 的基变换，也没有做设计文档 §6.3 的 Rest Pose Offset 补偿。真实 S32 姿态直接写到标准 Z-up 的 MMD 骨架上，角色会整体翻倒、压扁到原地（实测网格高度从 1.705 m 变成 0.641 m，见 `audit_evidence/mmd_real_s32.png`）。因此“真实 S32 姿态可写入”只能证明**字节写进去了**，不能证明**姿势是对的**。

**功能真实性分级**：

| 功能 | 文档/README 承诺 | 实测结论 | 判定 |
|---|---|---|---|
| Blender 扩展构建/安装/启用 | 可构建、可安装、可启用 | `dist/pose2rig-0.1.0.zip` 存在，SHA-256 与 README 一致；启用后 mock 与真实 S32 都能到 Done | ✅ 真实 |
| Mock 引擎 | 图片 → CanonicalPose → 相机 + 重定向 | 返回**固定 fixture**，不读取图片内容；只替换 image 尺寸并写 warning | ⚠️ 测试桩，不是识别 |
| SMPLer-X 真实推理 | 真实 S32 单图推理跑通 | 真实图片可输出 55 关节、55 个 local 旋转、相机参数 | ✅ 推理数据链 |
| 真实姿态在目标骨架上的正确性 | 真实 S32 姿态可写入并应用 | 未做坐标系/rest 补偿；MMD 真实模型实测翻倒压扁 | ❌ 不成立 |
| 55 关节 CanonicalPose | 55 关节 | `smplx_rest_skeleton.json` 55；真实输出 55 | ✅ 真实 |
| 双手 30 关节映射 | 双手各 15 关节 | Mixamo/MMD 各 30 根手指可映射；VRM 只有 12 根（缺中指/无名指/小指共 18 根） | ⚠️ 分预设 |
| Mixamo / VRM / MMD 预设 | 三套预设 | Mixamo 52、VRM 34、MMD 51 名称映射；VRM/MMD 只用合成/Y-up 测试骨架验证过 | ⚠️ 部分 |
| 相机匹配 | 透视相机、背景垫图 | 合成测试通过；真实 pose 的相机对象/背景图可创建；无手动焦距/偏移/缩放控件 | ⚠️ 仅自动相机 |
| Preview / Apply / Cancel / Undo | 预览只写副本，Apply 才写骨架 | Generate 就直接写目标骨架；Apply 只 `undo_push` 并清空快照；Euler 模式的骨架 Cancel 无法恢复 | ❌ 语义不符 |
| 网格安全 | 不破坏模型网格 | 静态没有 mesh 写操作；合成蒙皮网格顶点/边面/顶点组/修改器不变 | ✅ 数据层真实 |
| 只影响骨骼数据 | （隐含） | 姿态写入只改 pose bone；但 Generate 默认 Auto Camera 会改 scene.camera 和渲染分辨率 | ⚠️ 不是严格“只骨骼” |
| 半身图 | 未明确承诺 | 半身裁切也返回 55 关节且无 warning；下半身/手指是模型脑补 | ❌ 不支持/不可信 |
| 多人 | 设计说报告警告 | 多人图无警告；默认取最大 bbox，其他人物被忽略 | ❌ 未实现 |
| 保存/加载 pose JSON | 支持 | 保存后加载回姿态，误差 < 1e-4（测试通过） | ✅ 真实 |
| 用户骨骼映射保存/加载 | 第一版包含 | 未实现（代码无 mappings 目录/无 UI） | ❌ 未实现 |
| 60 图质量/性能、B32 对比 | README 标记 ⏳ | 未做；只有零散单图结果 | ⏳ 未完成 |

## 1. 图片识别链路：到底怎么“识别一张图”

### 1.1 UI 入口

1. `ui/panels.py` 在 3D 视图 Sidebar 的 Pose2Rig 面板提供图片路径、目标骨架、Preset、Engine 等控件。
2. 点击 Generate → `ui/operators.py::_start_generate()`：
   - 检查图片存在、目标骨架非空；
   - 用 `bpy.data.images.load()` 读取图片像素尺寸（`_image_size`，`ui/operators.py:74`）；
   - 构造 `infer` 请求，包含 `image_path`、`image_width`、`image_height`、`include_fingers`、模型目录、repo 目录、variant、device；
   - 启动 `WorkerClient` 子进程（`ipc/client.py`），把请求写入 worker stdin。
3. Worker `worker/server.py` 读取 JSON lines，调用 `get_engine(name, config).infer(image_path, options)`，校验 `pose_result/v1` 后返回。

**重要事实**：插件本身没有实现神经网络推理。真实引擎是**壳**：`worker/engines/smplerx.py::_run_reference_inference()` 复制输入到临时目录的 `000000.jpg`，然后 `subprocess.run([sys.executable, "inference.py", ...])` 调用户提供的 SMPLer-X 源码（`_research/repos/SMPLer-X/main/inference.py`），从输出目录读取 `.npz` 和 meta JSON。模型、权重、Python 3.8 环境都不在 dist 包内。

### 1.2 Mock 引擎（默认）

- `ui/properties.py` 的 `engine` 默认值是 `"mock"`。
- `worker/engines/mock.py::MockEngine.infer()`：只检查图片存在，读取 `assets/fixtures/mock_pose.json`，把 fixture 原样返回；若 `image_size()` 解析出 PNG/JPEG 尺寸则替换 image 宽高，否则使用调用方传入的尺寸。
- `mock_pose.json` 是 **22 关节**的固定姿态（不是 55 关节），包含 `diagnostics.warnings = ["mock fixture, not a real inference"]`。
- 结论：Mock 是测试桩，**不能识别图片内容**，不能用于评估识别质量。

### 1.3 真实 SMPLer-X 路径

SMPLer-X `main/inference.py` 的实际流程（源码 `_research/repos/SMPLer-X/main/inference.py:77-183`）：

1. 用 mmdet Faster R-CNN（COCO person，cat_id=0）做人体检测；
2. `process_mmdet_results(..., multi_person=True)` 得到 bbox 列表，但 inference.py 默认 `--multi_person` 为 false，因此只取**面积最大的一个 bbox**；
3. `process_bbox()` 按 192×256 长宽比扩展 bbox；`generate_patch_image()` 裁切并缩放到网络输入；
4. SMPLer-X 模型输出 `smplx_root_pose / smplx_body_pose / smplx_lhand_pose / smplx_rhand_pose / smplx_jaw_pose / cam_trans`；
5. `inference.py` 保存 `smplx/000000_0.npz` 和 `meta/000000_0.json`（focal、princpt、bbox）。

插件适配器 `worker/engines/smplerx.py::prediction_to_pose()`：

- 读取 npz 的 `global_orient/body_pose/left_hand_pose/right_hand_pose/jaw_pose`（同时兼容 `smplx_*` 命名）；
- 用 Rodrigues 公式把轴角转 3×3 矩阵；
- 按 55 关节顺序拼成 `local_pose_rotations`：1 根 + 21 body + jaw + 2 eyes + 15 left hand + 15 right hand；
- 读取 meta 的 focal/princpt/bbox，生成 `camera`；
- 返回 `pose_result/v1`。

**限制**：
- 真实推理必须使用用户自己配置的 `worker_python`（SMPLer-X venv）和 `model_dir/repo_dir`；dist 包不带模型；
- `diagnostics.timings_ms` 永远返回 `{}`（没有实际计时）；
- `hands.confidence` 永远 `null`；
- `weights_sha256` 默认 `null`（operator 没有传），只有 `source_revision` 硬编码为 `064baef0...`；
- 默认 `--testset EHF` 是 SMPLer-X demo 配置，不代表针对任意画风/半身图训练。

## 2. 输出参数：`pose_result/v1` 到底是什么

真实 S32 输出的结构（以 `_models/smplerx/last_pose.json` 为例）：

```json
{
  "schema_version": "pose_result/v1",
  "request_id": "...",
  "engine": {
    "id": "smplerx",
    "runtime": "torch",
    "weights_sha256": null,
    "source_revision": "064baef0e4ab5277a3297691bc1d46ea5412586f"
  },
  "image": {"width": 330, "height": 759, "sha256": "..."},
  "conventions": {
    "units": "m",
    "rotation": "row_major_3x3",
    "camera": "x_right_y_down_z_forward",
    "handedness": "right"
  },
  "source_skeleton": {
    "joint_names": ["pelvis", "left_hip", "..."],
    "parents": [-1, 0, 0, "..."],
    "rest_positions": [[0.003, -0.351, 0.012], "..."],
    "rest_rotations": [[[1,0,0],[0,1,0],[0,0,1]], "..."]
  },
  "local_pose_rotations": [[[ ... 3x3 ... ]], "... 55 个 ..."],
  "root_translation": [0.0, 0.0, 0.0],
  "camera": {
    "fx_px": 13428.6, "fy_px": 13428.6,
    "cx_px": 167.33, "cy_px": 432.06,
    "sensor_fit": "AUTO", "sensor_width_mm": 36.0,
    "model_to_camera": [[1,0,0,0.03],[0,1,0,0.237],[0,0,1,36.72],[0,0,0,1]]
  },
  "hands": {"enabled": true, "confidence": null},
  "diagnostics": {"timings_ms": {}, "warnings": []}
}
```

参数含义：

| 字段 | 含义/用途 | 实测备注 |
|---|---|---|
| `image.width/height` | 原图像素尺寸 | UI 从 bpy 图像读取；Mock 若解析不了 WebP 则靠调用方传入 |
| `source_skeleton.joint_names` | 55 个 SMPL-X 关节名 | 顺序为 pelvis + 21 body + jaw + 2 eyes + 30 手 |
| `source_skeleton.parents` | 关节父索引 | 根为 -1，必须指向更早索引 |
| `source_skeleton.rest_positions` | SMPL-X 模板静息关节位置（米） | 实际是 **Y-up 的 SMPL-X 坐标**，不是 Blender Z-up |
| `source_skeleton.rest_rotations` | 静息关节旋转（3×3） | 当前 skeleton 全部是单位矩阵 |
| `local_pose_rotations` | 每个关节相对父的局部旋转（3×3） | 来自 SMPL-X 轴角；**未做相机/Blender 基变换** |
| `root_translation` | 根平移（米） | 适配器永远填 `[0,0,0]`；真实 `transl` 被放进 camera |
| `camera.fx_px/fy_px` | 像素焦距 | 适配器 `fy = fx`，忽略 meta 的第二个值 |
| `camera.cx_px/cy_px` | 主点像素 | 由 meta 的 princpt 得到 |
| `camera.model_to_camera` | 模型→相机齐次矩阵 | 适配器只填平移，旋转为单位矩阵；未做 OpenCV→Blender 旋转 |
| `hands.enabled` | 手指是否启用 | 由 include_fingers 决定 |
| `hands.confidence` | 手部置信度 | **永远 null**，没有置信度输出 |
| `diagnostics.timings_ms` | 各阶段耗时 | **永远空对象**，没有统计 |
| `diagnostics.warnings` | 警告 | 真实路径永远空列表 |

## 3. 骨骼映射：具体怎么映射

### 3.1 预设格式

`assets/presets/*.json` 的 `bone_mapping` 是「SMPL-X 源关节名 → 目标骨候选名列表」：

```json
{
  "bone_mapping": {
    "pelvis": ["Hips"],
    "spine1": ["Spine"],
    "left_shoulder": ["LeftArm"],
    "left_thumb1": ["LeftHandThumb1"]
  },
  "prefixes": ["mixamorig:", ""],
  "required_joints": ["pelvis", "spine1", "..."]
}
```

`core/blender_retarget.py::build_mapping()`：

1. `detect_preset()`：`J_Bip_` 开头 → VRM；日文 `センター/上半身/左腕/右腕` → MMD；`mixamorig:` 或 `Hips` → Mixamo；
2. 对每个源关节，按候选名和 prefix 找目标骨名；
3. `required_joints` 缺失直接 `RetargetError`；其它缺失静默跳过；
4. 返回 `target bone index → source joint index` 的映射。

实测映射数量（对完整 SMPL-X 55 源关节算）：

| 预设 | 身体骨 | 手指骨 | 合计 | 说明 |
|---|---:|---:|---:|---|
| Mixamo | 22 | 30 | 52 | 齐 |
| VRM | 22 | **12** | **34** | 缺 middle/ring/pinky 三组共 18 根 |
| MMD | 21 | 30 | 51 | 缺 spine3（MMD 无对应） |

### 3.2 重定向数学

`core/retarget_math.py` 的实际实现：

```text
rest_relative: rel_i = R_rest_parent^-1 · R_rest_i
source_world:  S_i = S_parent · rel_i · L_i
delta:         D_i = S_pose_i · S_rest_i^-1
target_world:  T_b = D_source(j) · B_rest_b   （映射骨）
               T_b = T_parent · B_rel_b       （未映射骨）
local_basis:   Basis_b = (T_parent · B_rel_b)^-1 · T_b
```

关键问题：

- 代码中**没有**设计文档 §6.3 的 `ΔR_offset = R_S,rest^-1 · R_T,rest`；直接把源世界旋转增量 `D_j` 乘到目标静息矩阵上。对同向 T-pose 的合成骨架勉强成立，对 A-pose/不同 rest 的 MMD/VRM 不成立。
- 代码中**没有** `A_b` 语义对齐矩阵；设计文档提到但未实现（`retarget_math.target_world` 只有 `D_j @ target_rest[i]`）。
- 代码中**没有**任何 `camera (x_right,y_down,z_forward) → Blender (x_right,y_depth,z_up)` 基变换；也没有处理 SMPL-X 模型自身 Y-up 轴。
- 代码中**没有**把目标 Armature Object 的 `matrix_world` 纳入 rest 计算（`_rest_arrays` 只读 `bone.matrix_local`），所以对象有旋转/缩放时 ground_snap 和 rest 对齐会进一步偏。

这三点合起来就是：**名称映射是存在的，但语义重定向不成立**。

## 4. 网格安全：是否破坏模型网格，是否只影响骨骼

### 4.1 静态证据

全插件源码中搜索：

- 没有 `bpy.data.meshes` 写入；
- 没有 `.data.vertices` / `.data.polygons` 修改；
- 没有 `bpy.ops.mesh`、`modifier_apply`、`transform_apply`；
- 没有 `mode_set(mode="EDIT")`（只有 `mode_set(mode="POSE")`）。

`core/blender_retarget.py::apply_pose()` 只写：

```python
pb.rotation_mode = "QUATERNION"
pb.rotation_quaternion = Matrix(basis[i]).to_quaternion()
...
root_pb.location = local
```

`clear_pose()` 只写 pose bone 的 rotation/location/scale。没有任何 mesh/rest/vertex group/shape key 写入。

### 4.2 实测：合成蒙皮网格

构造带 Armature 修改器、顶点组权重的网格，记录应用前/后：

- 网格顶点数：3（测试用三角面）；边 3；面 1；
- 顶点坐标：`BASE_UNCHANGED = True`；
- 顶点组、修改器 list、对象矩阵：不变；
- 评估后（depsgraph evaluated）顶点坐标：`EVAL_CHANGED = True`（说明是 Armature 修改器在变形，不是 mesh 数据被改）。

结论：**网格数据不会被破坏**。但这也意味着：如果目标骨架与网格没有正确的 Armature 修改器/权重，插件不会帮你修复绑定，只是“不动网格”。

### 4.3 实测：MMD 真实模型

- 模型：`D:/Models/爱莉希雅女仆/爱莉希雅女仆.pmx`，MMD Tools 导入；
- 骨架：499 骨；网格：25,595 顶点、30,864 面、453 个顶点组、1 个 `mmd_armature` 修改器；
- 应用 mock 姿态后：网格数据仍为 25,595 顶点、30,864 面、453 顶点组、1 修改器，顶点坐标逐字节不变；
- 评估后网格高度：rest 1.705 m，mock 1.705 m，真实 S32 0.641 m（见下节）。

### 4.4 “只影响骨骼数据”的真实答案

- **姿态写入部分**：是的，只写 pose bone 通道（rotation/location），不碰 mesh/rest。
- **整体 Generate 操作**：不是。默认 `auto_camera=True` 时还会：
  - 新建/更新 `Pose2Rig_Camera` 对象；
  - 设置 `scene.camera`；
  - 改 `scene.render.resolution_x/y/percentage`（实测 1920×1080 → 330×759）；
  - 加载参考图到 `bpy.data.images`（每次 Generate 都会 load，不释放）；
  - 切换并保持在 POSE 模式、选中 armature。
- **Reset**：会删除相机对象和相机 data。
- **Apply**：会 `bpy.ops.ed.undo_push`。

所以更准确的说法是：**“不修改网格/rest 数据”成立；“只影响骨骼数据”不成立**。

## 5. 半身图：能不能识别

### 5.1 代码层

- 没有半身/全身判断；
- 没有 visible/occlusion/confidence 字段；
- 没有 missing joint 策略；
- SMPLer-X 的 `process_bbox()` 总是把 bbox 扩展成 192×256 的全身比例；半身图也会被扩展成含大量空白/背景的“全身框”；
- 模型输出固定 55 关节，不会因为腿不在画面里就少输出。

### 5.2 实测

将 `person_left.jpg`（330×759）裁成上半身（330×402），用同一个真实 S32 引擎跑：

- 返回 55 关节，`hands=true`；
- 没有 warning；
- camera fx=8301.91，主点 (151.65, 229.0)；
- 左/右膝角度 28.3° / 31.1°，脚踝 9.7° —— 下半身完全不在图像内，但模型仍给出了“膝盖弯曲”的数值；
- 结论：**接口上能跑，语义上不可信**。当前插件不支持半身图识别，应明确提示“需要全身图/下半身不可见时只使用上半身关节”。

## 6. 多人 / 无人 / 失败路径

- 多人：`inference.py` 默认 `--multi_person` 为 false，`process_mmdet_results` 取面积最大的 bbox；插件没有对检测数量做判断。实测 `person_left.jpg` 画面内有多名人物，输出 `diagnostics.warnings = []`。设计文档 §2 的“多人时报告警告”**未实现**。
- 无人：mmdet 无 bbox 时 `inference.py` 不写 npz；插件 `_run_reference_inference` 会抛 `EngineUnavailable("SMPLer-X inference produced no smplx npz output")`。这是失败路径，但没有专门 UI 提示/重试。
- 图片损坏：UI 的 `bpy.data.images.load` 会抛异常并显示 `Error: cannot read image`，这条有保护。
- Worker 崩溃/超时：`WorkerClient` 有 180 s 超时和 terminate；但 `SmplerXEngine` 内部允许 900 s，客户端 180 s 永远先到，慢机器上会被误杀。
- GPU OOM/无 GPU：没有专门检测/提示，只会变成 worker 的通用错误。

## 7. 关键缺陷清单（按优先级）

### P0-1 真实 S32 姿态坐标系未转换（阻断真实功能）

**证据**：

- `worker/engines/smplerx.py::prediction_to_pose()` 直接把 SMPL-X 轴角转矩阵后填入 `local_pose_rotations`（第 81–93 行），没有做任何坐标基变换；
- `core/blender_retarget.py::apply_pose()` 把这些矩阵直接用于 `compute_target_basis()`（第 164–171 行）；
- 真实 S32 结果 `last_pose.json` 的 pelvis 旋转角为 **177.4°**（所有真实样本都在 171–177°，这是相机 Y-down / SMPL-X Y-up 的体现）；
- 把该姿态应用到 Z-up 的 MMD 真实骨架（`爱莉希雅女仆_arm`，499 骨）：
  - rest bbox：z = -0.002 … 1.705（高 1.707 m）
  - 真实 S32 bbox：z = -0.294 … 0.641（高 0.935 m）
  - 渲染 `audit_evidence/mmd_real_s32.png`：角色整体翻倒/蜷缩在画面下方，已不是可用的站姿。
- 对照：mock fixture 因 root 近似单位旋转，bbox 仍为 1.705 m，所以现有 mock/headless 测试**完全测不出这个问题**。

**影响**：真实引擎的“识别”输出不能用于标准 Blender 角色；这是当前插件最核心的真实性缺口。

**建议**：建立明确的坐标约定层：

1. 把 SMPL-X 的 `rest_positions` / `local_pose_rotations` 从 SMPL-X/相机坐标转换到目标 armature 空间；
2. 按设计文档 §6.3 用 `R_obj * B_matrix_local` 计算 source/target rest，再做 `ΔR_offset`；
3. 先在一个 Z-up 的 Mixamo/MMD 骨架上做 2D 重投影 + 正面渲染验收，再谈真实质量。

### P0-2 半身图无支持，且静默输出全身脑补

见 §5。建议增加输入质量门：检测 bbox 高度/宽高比、关键点可见性；若下半身不可见则只映射上半身并在 UI 明确警告，不要静默给出全身 55 关节。

### P0-3 Apply/Cancel 语义不符 + Euler 骨架无法恢复

- `ui/operators.py::_start_generate()` 不创建快照；快照是在 worker 返回后、`_apply_pose()` 内才创建（`_STATE["snapshot"] is None` 时）。设计文档说的是“Generate 前”快照。
- Generate 结果直接写目标骨架（`_poll_generate → _apply_pose → blender_retarget.apply_pose`），不是“只写临时副本”；Apply 只是在 `POSE2RIG_OT_apply` 里 `undo_push` 并清空 snapshot，**没有写姿态动作**。
- `pose_state.snapshot_pose()` 只保存 `rotation_quaternion/location/scale`，不保存 `rotation_euler`。实测把 Hips 设为 Euler XYZ (0.2,0.3,0.4) 后：
  - 应用前矩阵首行 `[0.879923, -0.32758, 0.344132, 0]`
  - Cancel 恢复后矩阵变成 `[1,0,0,0]`（单位矩阵）
  - `EULER_RESTORE = False`
- 连续两次 Generate 不 Apply：第二次不会更新 snapshot；Cancel 恢复到第一次 Generate 前，而不是第二次 Generate 前。
- 切换 target armature 后 `_STATE["armature"]` 被覆盖，旧骨架的预览姿态无法 Cancel。

**建议**：`snapshot_pose` 改存 `matrix_basis`（或同时存 rotation_euler/axis_angle）；`_start_generate` 开始就快照；每次 Generate 一个 generation id/快照；Apply 时显式确认写入并清理；切换 rig 时先恢复/提示。

### P1-1 Rest Pose / A-pose 补偿缺失

见 §3.2。`design_spec.md §6.3` 的 `ΔR_offset` 公式没有实现，MMD/VRM 的 A-pose 与 SMPL-X T-pose 差异未被补偿。MMD 真实模型应用 mock（小旋转）时 bbox 高度仍是 1.705 m，说明这类小旋转测试无法暴露 A-pose/坐标系问题；真实 S32 则完全失效。

### P1-2 VRM 手指映射缺口

`assets/presets/vrm.json` 的 `bone_mapping` 只有 `thumb1-3 / index1-3`，没有 `middle/ring/pinky`。完整 SMPL-X 源关节计算：

- VRM 映射 34 根（22 身体 + 12 手指）；
- Mixamo/MMD 分别 52/51 根（30 手指）。

如果 README/UI 的“双手 30 关节”被理解为所有预设通用，这是不成立的。建议补齐 VRM 手指候选名，或用 VRM 标准命名 `J_Bip_L_Middle1` 等。

另外，`detect_preset()` 的 AUTO 逻辑只认 `J_Bip_` 前缀的 VRM 和日文 `左腕/右腕` 的 MMD；按 `mmd_adapter.md` 自己的说明，MMD Tools 也可能导出 `腕.L/腕.R`，此时 AUTO 会检测失败，需要用户手动选 MMD。VRM 如果导入成小写 `hips`/`leftUpperArm` 也会检测失败（预设本身支持这些候选名，但 AUTO 不认）。

### P1-3 姿态滑块数学错误

`core/pose_modifiers.py::_scale_delta()`：

```python
q_delta = q_rest.inverted() @ q_pose
q_new = q_rest @ Quaternion(q_delta.axis, q_delta.angle * factor)
```

`pb.rotation_quaternion` 本身就是相对 rest 的局部旋转；不应该再乘 `q_rest`。实测：rest = 90° X、pose = 30° Y、factor=0.5 时应为 15°，实际得到 **48.46°**，轴向也错误。建议：

```python
q_pose = pb.rotation_quaternion
pb.rotation_quaternion = Quaternion(q_pose.axis, q_pose.angle * factor)
```

`shoulder_relax/spine_influence` 的“非累积”测试能过，但数值正确性不成立。

### P1-4 多人无警告、测试图不是单人

`person_left.jpg` 实际画面至少包含两名完整人物和局部人物，但输出 `warnings=[]`。`poc_implementation_spec.md` 的“多人时报告警告”未实现。建议在 adapter 里读取 mmdet 检测数量（需要改 inference.py 输出或单独 detector），并在 UI 显示“检测到 N 人，只取最大 bbox”。

### P1-5 相机参数细节

- `prediction_to_pose()` 对 focal 只取第一个值：`fx = _first(focal); fy = _first(focal)`（第 116–119 行）。meta 的第二个值被忽略，非方形像素/特殊相机时会错。
- `camera_builder._lens_mm()` 无论 `sensor_fit` 是 AUTO/HORIZONTAL/VERTICAL 都用 `fx_px`；VERTICAL 时应使用 `fy_px`。
- 没有手动焦距/画面偏移/角色缩放/地面高度控件；`poc_design.md` 第一版第 25 条承诺的这些手动修正**未实现**。
- `camera_builder.create_or_update_camera()` 每次都会把 scene.render.resolution 改成图片尺寸，是全局副作用。

### P2-1 文档与测试声明漂移

- `docs/poc_implementation_spec.md:165` 仍写“SMPLer-X 网络桥接尚未接真实权重”，但 README/实际已经跑通 S32（文档过期）。
- README 说“19 个单元测试 + 7 个 Blender headless 测试全部通过”基本属实（我们复跑 19 + 7 全绿），但仓库里还有第 8 个 `test_installed.py`；直接用 `--factory-startup` 跑会因扩展未启用而报 `'Scene' object has no attribute 'pose2rig'`，需要先 `addon_utils.enable("bl_ext.user_default.pose2rig")` 才能过。README 的“7 个”没有把这个测试算进去。
- `tools/test_smplerx_infer.py` 在我们第一次后台运行时卡住且没有产生 inference 子进程；直接调用 `SmplerXEngine.infer` 和 Blender 内插件级真实引擎路径都能成功。该测试工具本身需要排查。

### P2-2 日志/诊断/进度字段不真实

- `diagnostics.timings_ms` 永远空；
- `hands.confidence` 永远 null；
- `ui/properties.py` 的 `progress` 从未被更新，面板也没有展示进度；
- `engine.weights_sha256` 默认 null（operator 不传）；
- 失败时 status 文本可能是长错误串，不是结构化进度。

### P2-3 测试覆盖/数据问题

- 真实测试只有 `person_left.jpg`、`person_center.jpg`、`tests/picture/*.webp` 等少量样本，且 `person_left.jpg` 不是单人裁剪；
- 没有 60 图质量/性能报告，没有 B32 对比（README 自己标 ⏳）；
- 没有无 GPU/GPU OOM/Worker 崩溃/连续 20 次 Generate 的自动化回归；
- 没有真实 Mixamo FBX/VRM 资产测试（只用 `rig_helpers` 合成骨架，且合成骨架是 Y-up，不是 Blender 常见的 Z-up）。

## 8. 复跑记录与证据

### 8.1 单元测试

命令：

```powershell
cd D:\blender5.2\pose_plugin
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

结果：`Ran 19 tests in 0.130s — OK`。

### 8.2 Blender headless 测试

命令：

```powershell
& D:\blender5.2\blender.exe --background --factory-startup --python tests\blender_headless\test_core.py
# 以及 test_extension.py, test_ground.py, test_hands.py, test_operators.py, test_save_load.py, test_vrm.py
```

结果：

| 测试 | 关键输出 | 结果 |
|---|---|---|
| test_core.py | `TEST_CAMERA_OK 45.0 0.5 0.5 ...`；`ALL_CORE_TESTS_PASSED` | ✅ |
| test_extension.py | `FINAL_STATUS Done: 22 bones (mixamo)`，`HAS_POSE True` | ✅ |
| test_ground.py | `FOOT_Z [0.0, 0.0, 0.08, 0.08]`，`GROUND_SNAP_OK` | ✅ |
| test_hands.py | `HAND_INFO {'mapped_bones': 52 ...}`，`HAND_TEST_OK` | ✅ |
| test_operators.py | Apply/Cancel/Reset 全部 `diff 0.0`，`OPERATOR_TESTS_PASSED` | ✅ |
| test_save_load.py | `SAVE_LOAD_TEST_OK`，delta 0.0 | ✅ |
| test_vrm.py | `VRM_INFO {'mapped_bones': 22 ...}`，`VRM_RETARGET_OK` | ✅ |

### 8.3 已安装扩展测试

- 直接 `--factory-startup --python test_installed.py`：失败（Scene 无 pose2rig，因为扩展未启用）；
- 先 `addon_utils.enable("bl_ext.user_default.pose2rig", default_set=True)` 再执行：`INSTALLED_STATUS Done: 22 bones (mixamo)`，`INSTALLED_HAS_POSE True`。
- 同一已安装扩展 + 真实 S32（worker_python 指向 `_envs/smplerx`，model_dir/repo_dir 指向本地模型）：`FINAL Done: 22 bones (mixamo)`，`JOINTS 55`，`ENGINE smplerx` —— 说明真实 Worker IPC + Blender 应用链路本身能跑通，问题在姿态语义/坐标。

### 8.4 真实 S32 推理（直接引擎）

命令（实际使用）：

```powershell
cd D:\blender5.2\pose_plugin
& _envs\smplerx\Scripts\python.exe -u _research\audit_smplerx_image.py _research\test_images\person_left.jpg _models\smplerx\last_pose.json
```

结果：

- 55 关节，hands=true；
- `fx_px=13428.62`，主点 `(167.33, 432.06)`，`model_to_camera z=36.72`；
- 推理 ~28 秒（second run）/ ~33 秒（half-body）；
- pelvis 旋转角 `177.4°`（真实 S32 的 camera Y-down 特征）；
- `diagnostics.warnings=[]`。

### 8.5 真实 S32 半身裁切

命令：

```powershell
& _envs\smplerx\Scripts\python.exe -u _research\audit_smplerx_image.py _research\test_images\person_left_halfbody.jpg _research\audit_halfbody_pose.json
```

结果：55 关节，`fx=8301.91`，`cx=151.65, cy=229.0`，无 warning；膝盖角度 28.3°/31.1°（下半身不在图内）。

### 8.6 MMD 真实模型应用

- 模型：`D:/Models/爱莉希雅女仆/爱莉希雅女仆.pmx`；
- 导入：`bpy.ops.mmd_tools.import_model(...)`，499 骨、25,595 顶点、30,864 面；
- 映射：`APPLY {'mapped_bones': 51, 'preset': 'MMD'}`；
- bbox：rest `(-0.593,-0.292,-0.002)…(0.593,0.407,1.705)`；mock `(-0.675,-0.292,-0.002)…(0.597,0.407,1.705)`；real S32 `(-0.357,-0.488,-0.294)…(0.597,0.414,0.641)`；
- 渲染对照：`audit_evidence/mmd_rest.png`、`audit_evidence/mmd_mock.png`、`audit_evidence/mmd_real_s32.png`。

### 8.7 合成蒙皮网格数据完整性

- 结果：`BASE_UNCHANGED True`，`EVAL_CHANGED True`；
- 说明：mesh data 未被修改，只有 Armature 修改器导致 evaluated mesh 变形。

### 8.8 姿态滑块数值检查

- rest 90° X、pose 30° Y、factor 0.5；
- 期望 15°，实际 `THEIR_ANGLE 48.462347`，轴向 `(0.939,0.344,0.0)`，而正确应为 `(0.0,1.0,0.0)`。

## 9. 建议修复顺序

### P0（先做，否则不要对外说“真实可用”）

1. **规范坐标层**：明确 source 的 rest/pose 是在 SMPL-X 模型空间、SMPLer-X 相机空间还是 Blender 空间；在 `prediction_to_pose` 后统一做基变换，再进入重定向；以“2D 重投影误差 + 正面渲染”验收。
2. **实现 design_spec §6.3 的 Rest Pose Offset**：用 Armature Object 的 `matrix_world` 参与 rest 计算，处理 T-pose/A-pose；先在 MMD 和真实 Mixamo/VRM 模型上验收。
3. **半身图输入门**：增加 bbox/可见性/关键点检查；不支持时明确报“需要全身图”，不要静默返回全身 55 关节。
4. **预览/Apply/Cancel 重做**：Generate 前快照；`snapshot_pose` 存 `matrix_basis`（或完整 rotation_euler/axis_angle）；每次 Generate 独立快照；切换 rig 前提示/恢复。

### P1（质量与一致性）

5. 修 `_scale_delta` 的局部旋转公式，给 `shoulder_relax/spine_influence` 增加数值断言测试（不是只看“变了/回去了”）。
6. 补 VRM 的 middle/ring/pinky 手指映射；对 VRM 真实模型跑 30 手指测试。
7. 多人检测结果写入 `diagnostics.warnings`，UI 显示“检测到 N 人，使用最大 bbox”。
8. focal 同时读 fx/fy；`_lens_mm` 按 sensor_fit 选择 fx/fy；补 EXIF 方向处理。
9. 把 `diagnostics.timings_ms` 真实计时（detect、model、convert、retarget）；更新 progress。
10. 客户端超时与引擎超时统一（至少可配置，默认不小于模型冷启动时间）。

### P2（文档与测试）

11. 更新 README/实现规范：明确“Mock 不是识别”“真实引擎需要外部 repo/weights”“S32 已跑通但视觉未验收”。
12. 修 `test_installed.py` 的启用逻辑；把 `test_installed` 纳入或明确排除在“7 个测试”之外。
13. 用真正的单人全身图、半身图、多人图、无图/损坏图、无 GPU 场景建立固定回归集；补 B32 与 60 图报告。
14. 如果保留“自定义骨骼映射”第一版承诺，补 UI/持久化；否则从第一版范围移除。

## 10. 审查边界

- 本次审查针对**当前工作区代码与已安装扩展**，不代表未来版本。
- 真实 S32 只测了 `person_left.jpg` 及其半身裁切；没有做 60 图/B32/CPU/无 GPU/GPU OOM 的完整评测。
- MMD 测试使用本地模型，未评估模型自身物理/材质；只验证骨架映射与网格数据完整性。
- 动画/K 帧/约束/驱动器/形态键没有做完整回归；本次只覆盖静态姿态应用。

---

**一句话结论**：Pose2Rig 目前的“工程链路”是真实的（扩展、Mock、Schema、Worker、JSON、骨骼通道写入都跑得通），但“真实图片 → 正确 3D 姿态 → 目标角色”的核心功能还没有真实性：真实 S32 数据缺少坐标/rest 补偿，标准 Z-up 角色会翻倒；半身图、多人、VRM 手指、Apply/Cancel 等要么不支持，要么语义与文档不符。建议按第 9 节 P0 项修复并重新做视觉验收后，再对外描述为“可用的真实姿态插件”。

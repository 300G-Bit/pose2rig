# Pose2Rig PoC 设计（v1，2026-11-07）

- 状态：已确认；PoC 实现中
- 实现进度（2026-11-08）：M0–M3 的 Mock 链路已完成并通过测试；M4 的 SMPLer-X 布局检查/输出转换/参考推理桥已完成，等待 SMPL-X 模型与完整依赖

## 1. 目标与边界

### 1.1 目标

做一个可在 Blender 5.2.2 中安装、可完整走通“单张图片 → 3D 姿态 → 目标角色”的研究型 PoC，优先验证插件功能与质量，不追求商业指标。

### 1.2 已确认决策

- 研究型 PoC；不考虑商业许可与上架。
- 引擎先用 **SMPLer-X S32/B32**；不达标再评估更重引擎。
- 暂时忽略 1.2 GB 显存与 0.8 s 端到端门槛。
- 只承诺 **Blender 5.2.2 / Windows x64**；其它版本等插件完成后适配。
- 权重不在仓库内分发；研究环境由用户自行准备。

### 1.3 第一版包含

- 单张 PNG/JPEG/WebP，单人。
- 人物检测框、SMPL-X 身体 21 关节 + 根、双手各 15 关节（手部可关闭）。
- 目标骨架：Mixamo、VRM humanoid、MMD/PMX 三套预设；缺骨时报告并跳过。
- 透视相机、原图背景垫图、焦距/画面偏移/角色缩放/地面高度手动修正。
- 三个非破坏调整：`shoulder_relax`、`spine_influence`、`ground_snap`。
- Generate 异步预览、Apply 写入姿态、Cancel 恢复、Undo。
- 保存/加载 `pose_result/v1` JSON；保存/加载用户骨骼映射。
- 失败路径：无人、多人、图片损坏、Worker 崩溃、GPU OOM、无 GPU。

### 1.4 第一版不包含

- 视频、多人跟踪、面部表情、眼球、口型。
- ONNX 转换、TensorRT、跨平台打包、自动模型下载器。
- 商业授权、付费版功能切分。
- 4.2/4.5 兼容性测试。
- “像素级重合”“精准还原”的承诺。

## 2. 架构

```text
Blender Extension (Blender 5.2.2, Python 3.13)
  ui/panels.py, ui/operators.py, ui/properties.py
  ipc/client.py            # subprocess + JSON lines + timer 回收
  core/schema.py           # pose_result/v1 校验
  core/retarget_math.py    # 纯 numpy 3x3 数学，可单测
  core/blender_retarget.py # bpy 骨架读写
  core/camera_builder.py   # 相机/背景图/投影
  core/pose_modifiers.py   # 三个滑块
  assets/presets/*.json
        │ stdio JSON lines
        ▼
Worker (独立进程；PoC 可复用 Python 3.12 跑 mock)
  worker/server.py         # 请求循环、错误处理、日志
  worker/engines/base.py   # Engine 接口
  worker/engines/mock.py   # 确定性 fixture，先跑通全链路
  worker/engines/smplerx.py  # SMPLer-X S32/B32 适配器（后续接权重）
```

关键边界：

- Blender 进程不导入 `torch` / `onnxruntime` / `smplx`。
- Worker 不导入 `bpy`。
- Blender 只消费 `pose_result/v1`；不直接读模型原始输出。
- 所有 `bpy` 场景写操作只在主线程；后台线程只做进程与队列。
- 预览与 Apply 分离：预览只写副本/临时姿态，Apply 才写用户骨架并 push undo。

## 3. 数据契约（`pose_result/v1`）

必填字段：

- `schema_version`：固定 `pose_result/v1`。
- `request_id`：UUID。
- `engine`：`id`、`runtime`、`weights_sha256`（可空）、`source_revision`。
- `image`：`width`、`height`、`sha256`。
- `conventions`：`units`、`rotation`、`camera`、`handedness`。
- `source_skeleton`：`joint_names`、`parents`、`rest_positions`、`rest_rotations`（3×3 行主序）。
- `local_pose_rotations`：每个关节一个 3×3。
- `root_translation`：3 维，米。
- `camera`：`fx_px`、`fy_px`、`cx_px`、`cy_px`、`sensor_fit`、`sensor_width_mm`、`model_to_camera`（4×4）。
- `hands`：`enabled`、`confidence`（可为 null）。
- `diagnostics`：`timings_ms`、`warnings`。

校验规则：

- 所有 3×3 旋转矩阵必须是有限数、近似正交、行列式 ≈ +1；`model_to_camera` 是 4×4 刚体变换，只检查左上 3×3 正交且最后一行 [0,0,0,1]。
- 长度：`local_pose_rotations` 与 `source_skeleton.joint_names` 一致。
- 未知值用 `null`，不伪造。
- 校验失败：Worker 返回结构化错误；Blender 不修改场景。

## 4. 数学约定

### 4.1 重定向

源关节 `j` 到目标骨 `b`：

```text
D_j     = S_pose_j @ S_rest_j.inverted()
P_b     = D_j @ A_b @ B_rest_b
Basis_b = (P_parent @ B_rel_b).inverted() @ P_b
B_rel_b = B_parent_rest.inverted() @ B_rest_b
```

- `A_b` 为语义对齐；同构骨架用 identity；四肢按 rest 方向对齐，足按 yaw 对齐。
- 未映射骨：`P_b = P_parent @ B_rel_b`（保持 rest-relative）。
- 根位移按腿长比例缩放；不直接写源 pelvis 米制坐标。
- 写入 `pb.rotation_quaternion`，不写 `pb.matrix`，避免 depsgraph 时序问题。
- 不修改用户 rest pose，不 `transform_apply`。

### 4.2 相机

```text
lens_mm = fx_px * sensor_width_mm / max(W, H)   # sensor_fit='AUTO'
```

- 支持 `HORIZONTAL` / `VERTICAL` 两种显式 fit。
- 由 `model_to_camera` 求相机世界位置与旋转：`R_world = R^T @ diag(1,-1,-1)`，`C = -R^T t`。
- 用 `world_to_camera_view` 做回归：合成已知 3D 点，误差 < 1 px。

### 4.3 后处理

```text
q_delta = q_rest.inverted() @ q_pose
q_new   = q_rest @ Quaternion(q_delta.axis, q_delta.angle * factor)
```

- `shoulder_relax`：只作用于 collar 的 delta。
- `spine_influence`：只作用于 spine1–3 的 delta。
- `ground_snap`：用 `PoseBone.tail` 或 evaluated mesh 最低点，不用 `Bone.tail`。

## 5. 模块与文件

```text
pose_plugin/
  pose2rig_blender/
    blender_manifest.toml
    __init__.py
    ui/
      properties.py
      operators.py
      panels.py
      preferences.py
    ipc/
      client.py
    core/
      schema.py
      retarget_math.py
      blender_retarget.py
      camera_builder.py
      pose_modifiers.py
      pose_state.py
    worker/
      server.py
      engines/
        base.py
        mock.py
        smplerx.py
        registry.py
        model_layout.py
    assets/
      presets/mixamo.json
      presets/vrm.json
      fixtures/mock_pose.json
  tests/
    unit/test_retarget_math.py
    unit/test_schema.py
    blender_headless/test_core.py
    blender_headless/test_extension.py
    blender_headless/rig_helpers.py
```

## 6. 里程碑与验收

| 里程碑 | 交付 | 验收 |
|---|---|---|
| M0 | manifest、扩展注册、面板空壳 | Blender 5.2.2 安装并启用无异常 |
| M1 | schema、mock worker、Generate 按钮、异步状态 | 点击 Generate 不卡 UI；能读到 mock 结果 |
| M2 | 相机、重定向、预览（含手动焦距/偏移/角色缩放/地面高度） | 合成角色摆出 mock 姿态；相机投影 < 1 px |
| M3 | Mixamo + VRM 预设、三个滑块、Apply/Cancel/Undo、JSON 保存/加载、用户映射 | 两套预设均可用；滑块不累积；Undo 恢复；JSON 往返一致 |
| M4 | SMPLer-X S32/B32 适配器 | 真实图片输出合法 JSON；记录耗时/显存；覆盖无 GPU/GPU OOM/取消/崩溃 |
| M5 | 60 图质量与稳定性报告 | 明确通过/失败项，不包装成商业完成版 |

## 7. 测试

- 纯 Python：旋转矩阵/四元数往返、父链、rest offset、左右镜像、非均匀缩放。
- Blender headless：相机三 fit、横竖方图、重定向 golden rig、扩展注册、UI 冒烟。
- 集成：无人/多人/损坏图/无 GPU/Worker 崩溃/取消/超时；连续 20 次 Generate 无泄漏。
- 所有 Blender 自动化使用 `--factory-startup`，避免用户配置中的插件污染。

## 8. 风险与处理

| 风险 | 处理 |
|---|---|
| SMPLer-X 环境重、Windows 依赖难装 | 先 mock 跑通插件；真实环境单独 venv；失败不阻塞 UI 开发 |
| SMPL-X 模型权重需要注册 | 用户自行准备；代码只读配置路径，不下载 |
| 重定向数学错 | 先过 golden tests，再扩预设 |
| 相机投影偏 | 合成测试 + 手动焦距/偏移兜底 |
| 目标骨架变体多 | 缺骨报告 + 自定义映射；不承诺 Auto Detect |
| 用户配置插件干扰 | 测试统一 `--factory-startup` |

## 9. 待定

- SMPLer-X 权重放哪个目录（建议 `pose_plugin/_models/smplerx/`，加入 .gitignore）。
- 真实推理用 Python 3.10 venv 还是 3.12（先测依赖兼容）。
- 第一个真实测试角色用哪个 VRM/Mixamo 文件。

## 10. 参考文档

- [实现规范（接口/协议/验收）](poc_implementation_spec.md)
- [原始调研](blender_3d.md)
- [工程设计说明书](design_spec.md)
- [复核报告与 v2 方案](design_spec_review.md)

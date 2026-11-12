# EGM Goldfish 评审记录（poc_design.md）

评审日期：2026-11-07
评审对象：`docs/poc_design.md`
评审方式：EGM（Elephant-Goldfish Model）三个冷上下文 Goldfish 角色，只读评审
- Design Critic：架构、失败模式、隐藏假设
- Implementation Readiness：实现就绪度、接口/协议/验收
- Structural：章节结构、代码围栏、表格一致性

## 结论

三份评审一致认为：`poc_design.md` 作为方向说明可用，但**不是实现就绪文档**。主要缺口是接口签名、IPC 协议、错误码、预览/撤销语义、预设 schema 和可执行验收。该结论已转化为 `poc_implementation_spec.md`，并在代码中落地。

## 关键发现与处理

| # | 评审发现 | 严重度 | 处理 |
|---|---|---|---|
| 1 | 没有 IPC 请求/响应契约、握手、错误 envelope | Blocker | 已写入 `poc_implementation_spec.md` §2；`worker/server.py` 实现 hello/ping/infer/shutdown/error |
| 2 | 缺少 person detection / bbox / 多人策略 | Blocker | Mock 使用外部 bbox；SMPLer-X adapter 要求 `options.bbox_xyxy`；检测器列为下一里程碑 |
| 3 | 手部 30 关节无法表达 | Blocker | `smplx_rest_skeleton.json` 为 55 关节；`prediction_to_pose` 支持双手；`test_hands.py` 验证 52 骨映射 |
| 4 | 旋转帧定义不清 | Blocker | 规范 §1.1/§4；代码统一 `local_pose_rotations` + FK 累积 |
| 5 | 校验规则对 4x4/点云不成立 | Major | `schema.py` 分离 3x3 旋转与 4x4 rigid transform 校验 |
| 6 | A_b 未约束 twist | Major | 当前同构/rest offset 路径用 identity；twist golden test 留待 P2 |
| 7 | 相机主点/纵横比/EXIF 未处理 | Major | 已实现 `shift_x/y` 与 `match_resolution`；EXIF/畸变留待后续 |
| 8 | 异步生命周期/取消/超时未定义 | Major | `WorkerClient` 线程 + 超时 + terminate；UI 用 `bpy.app.timers` 回收 |
| 9 | 预览/Apply/Cancel/Undo 未定义 | Major | `pose_state.py` 快照；`test_operators.py` 验证 |
| 10 | Worker 环境/版本/模型路径未定义 | Major | `preferences.py` + `model_setup.md` + `model_layout.py` |
| 11 | 根位移/贴地未定义 | Major | 腿长比例 + `PoseBone.tail`；`test_ground.py` |
| 12 | 姿态精度无指标 | Major | M5 指标待定；PoC 先用合成/人工评审 |
| 13 | 目标骨架变体/roll/约束 | Major | 预设 + `required_joints`；Mixamo/VRM 测试通过 |
| 14 | 测试缺保存/加载/手指/VRM | Nit | 已补 `test_save_load.py`、`test_hands.py`、`test_vrm.py` |
| 15 | 引擎 variant/输入尺寸/权重哈希 | Nit | `preferences.variant`、`model_layout`、`weights_sha256` |

## 仍未关闭

- 真实 SMPLer-X 网络桥接（需要用户提供 SMPL-X 模型文件与完整依赖）。
- Person detector 与多人策略。
- 手指 PCA→旋转（若权重使用 PCA）。
- 真实 60 图质量/性能报告。

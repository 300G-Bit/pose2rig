# Pose2Rig 修复与测试记录（2026-11-11）

- 版本：0.2.2
- 交付包：dist/pose2rig-0.2.2.zip
- SHA-256：2483759363A8B9D0CFB4043B717BFD770194BCE3D88C1E3B9994149FD24B3F85
- 输入测试图：D:/blender5.2/pose_plugin/tests/picture/78310a55b319ebc4b7455cf34668d8fc1e178a82b801.webp（1895x785，WebP）
- 准确度归因：见 `accuracy_attribution_20261111.md`

## 1. 修复清单

| 优先级 | 修复内容 | 代码位置 |
|---|---|---|
| P0-1 | 增加相机系→Blender 世界系 B 矩阵、SMPL-X 静止姿态 R_rest_cam；SMPLer-X 适配器输出 rest_rotations=R_x(180°)、root local=R_rest_cam^T·global_orient；retarget 支持 world_from_source 与 target_object_rotation | worker/engines/smplerx.py、core/retarget_math.py、core/blender_retarget.py |
| P0-1 | 修复相机位置/旋转：C=B·(-R^T·t)、R_wc=B·R^T·diag(1,-1,-1)；镜头 fit 支持 fy | core/camera_builder.py |
| P1-2 | VRM 补齐 middle/ring/pinky 18 根手指，合计 52 骨；detect_preset 改为 required_joints 候选骨评分，兼容 MMD .L/.R 与 VRM 小写命名 | assets/presets/vrm.json、core/blender_retarget.py |
| P1-2b | MMD 胸段映射修正：`spine3` → `上半身2`（原 `spine2` 导致胸段方向错位），`spine2` 不再 required | assets/presets/mmd.json |
| P1-3 | 修正 _scale_delta：直接缩放 pb.rotation_quaternion，不再重复乘 q_rest | core/pose_modifiers.py |
| P0-2 | snapshot_pose/restore_pose 改为 matrix_basis；Generate 前抓快照；Cancel 恢复分辨率、场景相机和插件相机；Apply 清理快照 | core/pose_state.py、ui/operators.py |
| P0-3 | 增加 input_quality（visible_joint_ratio、lower_body_visible、bbox_touches_edges、detected_persons）；AUTO 模式半身图自动只映射上半身；多人数写入 diagnostics.warnings | core/pose_metrics.py、worker/engines/smplerx.py、core/blender_retarget.py |
| P0-3 | inference.py meta 增加 num_persons；patch_smplerx_runtime.py 同步加入补丁 | _research/repos/SMPLer-X/main/inference.py、tools/patch_smplerx_runtime.py |
| P1-1 | apply_pose 将世界空间增量转换回 armature object 空间；ground_snap 使用 matrix_world；新增 A_b rest 方向对齐（source child 方向，跳过腿/颈/头）；`mute_ik` 改为可选调试开关（默认 False，保留 MMD 踮脚脚型） | core/blender_retarget.py、core/retarget_math.py、core/pose_modifiers.py |
| P2 | diagnostics.timings_ms 记录 probe/inference/convert/total；progress 更新；worker timeout 可配置（默认 600s） | worker/engines/smplerx.py、ui/operators.py、ui/preferences.py |

## 2. 测试结果

- 单元测试：22 个通过（含 test_frame_contract.py 与 rotation_between 测试）。
- Blender headless：8 个全部通过（test_core、test_extension、test_operators、test_vrm、test_hands、test_ground、test_save_load、test_installed）。
- 已安装扩展 + 真实 S32：Done: 22 bones (MIXAMO)，55 关节，input_quality 正常，timings 正常。
- 真实 S32 + MMD 模型：51 骨映射，rest bbox Z -0.002..1.705 m；应用测试图姿态后：`上半身/上半身2/腕/ひじ/手首` 方向与 source pose 误差 **0.0°**（A_b + MMD 胸段映射修正）；`首/頭` 残余约 8–9°；默认保留 MMD IK，脚型/踮脚不被 mute 改变。

## 3. tests/picture 验收

- 原图为 WebP 1895x785；Blender 可直接读取，worker 现在会自动转成 JPEG 再送 SMPLer-X（转换失败则原样复制）；已直接用原 WebP 跑通，55 关节，约 34 s。
- 插件完整路径：STATUS Done: 51 bones (MMD)，PROGRESS 1.0。
- 检测到 2 人：WARN detected 2 persons; only the largest bbox is used。
- 输出图：
  - docs/test_picture_plugin_render.png：按推理相机渲染（1895x785）
  - docs/test_picture_mmd_fullbody.png：正面全身纹理渲染（800x1100）
  - docs/test_picture_mmd_closeup.png：正面近景纹理渲染（560x760）
  - docs/test_picture_mmd_textured.png：按推理相机渲染的纹理版本（1895x785）
  - docs/test_picture_compare.png：源图与纹理渲染的左右对照（1349x934）

## 4. 仍需注意

- A_b 已实现（source child 方向、仅上半身非颈/头骨）；脚部 yaw 尚未单独标定；`mute_ik=True` 会改变脚型，默认不要使用。
- hands.confidence 仍为 null（SMPLer-X 不输出该置信度），UI 不伪造。
- 60 图质量/性能报告与 B32 对比仍未完成。
- 真实 S32 + MMD 的手部/裙摆等细部仍可能出现穿模或姿态不自然，需要逐图验收。

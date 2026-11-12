# Pose2Rig PoC

Blender 5.2.2 单图转 3D 骨骼姿态插件的研究型 PoC。

## 当前状态

- ✅ Blender Extension 可构建、可安装、可启用（v0.2.2）
- ✅ Mock 引擎：图片 → CanonicalPose → 相机 + Mixamo/VRM/MMD 重定向 → 预览/Apply/Cancel/Undo
- ✅ 55 关节 CanonicalPose 与双手 30 关节映射
- ✅ SMPLer-X 模型布局检查与 `prediction_to_pose` 转换
- ✅ SMPL-X v1.1 / SMPL v1.1.0 / 对应关系文件已整理到 `_models/smplerx`
- ✅ S32/B32 权重与 mmdet 检测器已准备；`check_model_layout.py` 显示两档 layout ready
- ✅ SMPLer-X 独立环境已配置：Python 3.8 + torch 1.12 cu113 + mmcv-full 1.7.1 + mmdet 2.26 + mmpose 0.28
- ✅ 真实 S32 单图推理已跑通；SMPL-X 相机系 → Blender Z-up 的静止姿态与相机坐标已修正，真实姿态在 MMD 模型上高度约 1.52 m（rest 1.71 m）
- ✅ MMD/PMX 标准比例模型适配：51 骨（21 身体 + 30 手指）映射通过
- ✅ VRM 手指补齐到 30 根；预设自动检测改为候选骨评分
- ✅ Preview/Apply/Cancel 改为 matrix_basis 快照；半身/多人输入质量门已加入
- ⏳ 真实 60 图质量/性能报告与 B32 对比

当前测试：**22 个单元测试 + 8 个 Blender headless 测试全部通过**。交付包：`dist/pose2rig-0.2.2.zip`（SHA-256 `2483759363A8B9D0CFB4043B717BFD770194BCE3D88C1E3B9994149FD24B3F85`）。

## MCP 验证

Blender 5.2.2 官方 MCP 监听 **127.0.0.1:9896**。使用轻量客户端：

```powershell
python tools/mcp_official_client.py --file tests/blender_mcp/mcp_smoke.py
```

已实测：官方 MCP 返回 `blender=[5,2,2]`，插件面板存在，Mock 与真实 S32 均返回 `Done: 22 bones (mixamo)`。

## 快速开始（Mock）

1. 构建扩展：
   ```powershell
   cd D:\blender5.2\pose_plugin
   & 'D:\blender5.2\blender.exe' --command extension build --source-dir pose2rig_blender --output-dir dist
   ```
2. Blender > Preferences > Extensions > Install from Disk，选择 `dist/pose2rig-0.2.2.zip`。
3. 3D View > Sidebar > Pose2Rig：选择图片、目标骨架、引擎 Mock，点击 Generate。
4. 用 Shoulder Relax / Spine Influence / Snap Feet 调姿态；Apply 保留，Cancel 恢复。

## 测试

```powershell
python -m unittest discover -s tests/unit -p "test_*.py" -v
& 'D:\blender5.2\blender.exe' --background --factory-startup --python tests\blender_headless\test_core.py
& 'D:\blender5.2\blender.exe' --background --factory-startup --python tests\blender_headless\test_extension.py
& 'D:\blender5.2\blender.exe' --background --factory-startup --python tests\blender_headless\test_operators.py
```

## 文档

- [PoC 设计](docs/poc_design.md)
- [实现规范](docs/poc_implementation_spec.md)
- [SMPLer-X 模型准备](docs/model_setup.md)
- [S32 真实单图测试记录](docs/real_s32_report.md)
- [MMD 骨架适配说明](docs/mmd_adapter.md)
- [2026-11-11 测试记录](docs/test_results_20261111.md)
- [EGM 评审记录](docs/egm_review_poc.md)
- [design_spec 复核报告](docs/design_spec_review.md)
- [功能真实性审查记录（2026-11-11）](docs/feature_audit_20261111.md)
- [审查问题分析（2026-11-11）](docs/audit_issue_analysis.md)
- [修复与测试记录（2026-11-11）](docs/fix_report_20261111.md)
- [识别 vs 映射准确度归因（2026-11-11）](docs/accuracy_attribution_20261111.md)

## 本地资产与许可

本仓库不包含以下受许可限制的资产，`.gitignore` 已将其排除：

- `pose2rig_blender/assets/models/ue_mannequin/`：Unreal Engine 自带小白人模型，受 **Unreal Engine EULA** 约束，仅限本机开发测试，请从本地 UE 安装内容自行导出。
- `pose2rig_blender/assets/skeleton/smplx_rest_skeleton.json`：由 SMPL-X neutral `template_J` 派生，**SMPL-X 许可禁止再分发**。请在本机准备 SMPL-X 模型后生成：

  ```powershell
  python tools/make_smplx_rest_skeleton.py --model _models/smplerx/common/utils/human_model_files/smplx/SMPLX_NEUTRAL.npz
  ```

## 许可

PoC 仅用于研究。SMPLer-X、SMPL-X、WiLoR 等资产各有独立许可；不要将非商业权重打包进商业发行物。

# S32 真实单图测试记录

日期：2026-11-09
环境：Python 3.8.20 / torch 1.12.0+cu113 / mmcv-full 1.7.1 / mmdet 2.26.0 / mmpose 0.28.0

## 输入

- 原图：`_research/repos/CameraHMR/demo_images/pexels-bertellifotografia-3856033.jpg`
- 单人裁剪：`_research/test_images/person_left.jpg`（330x759）

## 结果

通过 `pose2rig_blender/worker/server.py` 的 `smplerx` 引擎调用 SMPLer-X `main/inference.py`：

- 输出：55 个 SMPL-X 关节，hands=true
- root_pose、body_pose、左右手姿态均为非单位旋转
- 相机：fx_px=13430，主点 (167, 432)，model_to_camera 使用 transl
- 参考推理进度：约 29.2 秒/张（首次加载模型；RTX 3060 Laptop）

插件内应用结果（通过 Blender 5.2.2 官方 MCP，端口 9896）：

- 测试骨架（22 个 Mixamo 骨、无手指）：Done: 22 bones (mixamo)
- CanonicalPose 55 关节、hands=true
- 相机 Pose2Rig_Camera 已创建
- 左手指尖位置为 [0.437, 0.863, -0.204]，与 rest 明显不同
- 截图工具在当前 Blender 窗口返回的是旧帧，本次未保留截图；以 MCP stdout/姿态数值为准。

## 已修复的兼容问题

1. torchgeometry 旧版 bool 减法与 torch 1.12 不兼容
2. SMPLX_to_J14.pkl 由系统 numpy 2.x 生成，venv numpy 1.23 无法读取；改用 venv 重新生成
3. mmcv 的 yapf 配置 dump 在 Windows 路径下报 unicodeescape
4. utils.vis 依赖 pyrender/EGL，Windows 无 EGL；改为可选导入/跳过渲染
5. SMPLer-X 仓库通过目录联接读取 _models/smplerx 下的模型与权重

## 下一步

- 用 person_center.jpg 或更多单人物图做质量对比
- B32 对照
- 60 图数据集与 2D 重投影可视化

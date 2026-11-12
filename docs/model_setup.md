# SMPLer-X 研究环境与模型布局

本文件说明如何准备 SMPLer-X S32/B32 的本地环境。**仅用于研究 PoC，不用于商业分发**。SMPLer-X 代码与 SMPL-X 资产各有独立许可，使用前请自行确认。

## 1. 目录布局

```text
pose_plugin/_models/smplerx/
  pretrained_models/
    smpler_x_s32.pth.tar              # 必需（本机已下载）
    smpler_x_b32.pth.tar              # 可选
    mmdet/
      faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth
      mmdet_faster_rcnn_r50_fpn_coco.py
  common/
    utils/
      human_model_files/
        smpl/
          SMPL_NEUTRAL.pkl            # 必需
          SMPL_MALE.pkl               # 必需
          SMPL_FEMALE.pkl             # 必需
        smplx/
          SMPLX_NEUTRAL.npz           # 必需
          SMPLX_MALE.npz              # 必需
          SMPLX_FEMALE.npz            # 必需
          SMPLX_to_J14.pkl            # 必需
          MANO_SMPLX_vertex_ids.pkl   # 必需
          SMPL-X__FLAME_vertex_ids.npy # 必需
          SMPLX_NEUTRAL.pkl           # 可选（v1.1 包自带）
          SMPLX_MALE.pkl              # 可选
          SMPLX_FEMALE.pkl            # 可选
```

## 2. 下载（按顺序）

### 2.1 SMPL-X v1.1 模型

在 https://smpl-x.is.tue.mpg.de/download.php 登录后下载：

- **`models_smplx_v1_1.zip`**（SMPL-X Model v1.1，NPZ + PKL 包）
  - 解压后得到 `models/smplx/SMPLX_NEUTRAL.npz`、`SMPLX_MALE.npz`、`SMPLX_FEMALE.npz`
  - 同一包通常还含对应的 `.pkl`；若包内有 `smplx_npz.zip` / `smplx_pkl.zip`，再解压一层
  - 不需要 `SMPLX_NEUTRAL_2020.npz`（除非使用 2020 特殊模型）

### 2.2 SMPL-X 与 MANO / FLAME 的对应关系

同一页面下载：

- **`smplx_mano_flame_correspondences.zip`**
  - 解压得到 `MANO_SMPLX_vertex_ids.pkl` 和 `SMPL-X__FLAME_vertex_ids.npy`

### 2.3 SMPLX_to_J14.pkl

不在 SMPL-X 页面，来自 expose 的 “Preparing the data”：

- https://github.com/vchoutas/expose#preparing-the-data
- 文件约 4.69 MB，放到 `human_model_files/smplx/SMPLX_to_J14.pkl`
- 本机没有 ExPose 原文件，已从 `SMPLX_NEUTRAL.npz` 的 `J_regressor` 生成一个 `(14, 10475)` 的研究用映射；正式 MPJPE 评测请替换为 ExPose 原文件。

### 2.4 SMPL 基础模型（SMPLer-X 也会实例化 SMPL）

在 https://smpl.is.tue.mpg.de/ 注册后下载：

- **`SMPL_python_v.1.1.0.zip`**
  - 解压得到 `SMPL_NEUTRAL.pkl`、`SMPL_MALE.pkl`、`SMPL_FEMALE.pkl`
  - 这些是 `SMPLer-X/common/utils/human_models.py` 初始化 `SMPL()` 所需，不是可选的

### 2.5 检测器

- mmdet Faster R-CNN checkpoint：
  https://download.openmmlab.com/mmdetection/v2.0/faster_rcnn/faster_rcnn_r50_fpn_1x_coco/faster_rcnn_r50_fpn_1x_coco_20200130-047c8118.pth
- config：
  https://raw.githubusercontent.com/openxrlab/xrmocap/main/configs/modules/human_perception/mmdet_faster_rcnn_r50_fpn_coco.py
- 放到 `pretrained_models/mmdet/`

### 2.6 SMPLer-X S32 / B32 权重

- S32: https://huggingface.co/caizhongang/SMPLer-X/resolve/main/smpler_x_s32.pth.tar
- B32: https://huggingface.co/caizhongang/SMPLer-X/resolve/main/smpler_x_b32.pth.tar
- 本机已下载 S32 到 `_models/smplerx/pretrained_models/smpler_x_s32.pth.tar`，大小 384,315,279 bytes，SHA-256 = `1C78569F4E7B6E22E7166B55F322E5D5E019073B8D1A430A6926F93B4C86AA62`。
- 本机已下载 B32 到 `_models/smplerx/pretrained_models/smpler_x_b32.pth.tar`，大小 1,235,500,495 bytes，SHA-256 = `53BAF53545424F39C4BB80963A068B947BE37AA49A64E622280CB1E0D5A018B7`。
- mmdet checkpoint 大小 167,287,506 bytes，SHA-256 = `047C8118FC5CA88BA5AE1FAB72F2CD6B070501FE3AF2F3CBA5CFA9A89B44B03E`。
- ViTPose 权重只在训练/初始化时需要；SMPLer-X 的 demo 推理加载完整 `smpler_x_*.pth.tar`，不需要单独的 `vitpose_small.pth`。

## 3. Worker 环境（已配置）

不要装进 Blender Python。使用独立 Python 3.8 环境：

```powershell
cd D:\blender5.2\pose_plugin
.\tools\setup_smplerx_env.ps1
```

脚本会创建 `_envs/smplerx` 并安装以下已验证组合：

| 组件 | 版本 |
|---|---|
| Python | 3.8.20 |
| torch / torchvision / torchaudio | 1.12.0+cu113 / 0.13.0+cu113 / 0.12.0+cu113 |
| mmcv-full | 1.7.1 |
| mmdet | 2.26.0 |
| mmpose | 0.28.0（SMPLer-X 的 transformer_utils） |
| numpy / scipy / yapf | 1.23.5 / 1.10.1 / 0.40.1 |

安装后运行 `tools/patch_smplerx_runtime.py`，处理三处 Windows 兼容问题：

1. torchgeometry 的 bool 减法；
2. mmcv 在 Windows 反斜杠路径下的 yapf 配置转储；
3. pyrender/EGL 不可用时的可视化导入与渲染跳过。

另外，SMPLer-X 代码默认从仓库内的 `common/utils/human_model_files` 与 `pretrained_models` 读取文件。本机用目录联接把它们指向 `_models/smplerx`：

```powershell
cmd /c mklink /J "pose_plugin\_research\repos\SMPLer-X\common\utils\human_model_files" "pose_plugin\_models\smplerx\common\utils\human_model_files"
cmd /c mklink /J "pose_plugin\_research\repos\SMPLer-X\pretrained_models" "pose_plugin\_models\smplerx\pretrained_models"
```

**不要**在 Blender 内安装这些依赖；Blender 只通过 `Worker Python` 偏好调用 `_envs/smplerx/Scripts/python.exe`。

## 4. 在插件中配置

1. Edit > Preferences > Add-ons > Pose2Rig > Worker Python 选择上述环境的 `python.exe`。
2. SMPLer-X Model Directory 选择 `pose_plugin/_models/smplerx`。
3. SMPLer-X Repo 选择 `pose_plugin/_research/repos/SMPLer-X`。
4. Variant 选 S32 或 B32。
5. 回到 3D View > Pose2Rig，引擎选 SMPLer-X，点击 `Check Engine Files`。

## 5. 当前状态

- `worker/engines/model_layout.py` 已能检查文件是否齐全。
- `worker/engines/smplerx.py` 的 `prediction_to_pose()` 已能把 SMPLer-X 的旋转参数转成 `pose_result/v1`。
- 已通过 `main/inference.py` 子进程桥跑通 **S32 真实单图**（55 关节输出）。
- 下一步：60 图质量/稳定性报告、B32 对比、2D 重投影可视化。

## 6. 校验

```powershell
Get-ChildItem -Recurse -File pose_plugin\_models\smplerx | Select-Object FullName,Length
python -c "from pose2rig_blender.worker.engines.model_layout import check_layout; print(check_layout(r'D:\blender5.2\pose_plugin\_models\smplerx','s32'))"
```

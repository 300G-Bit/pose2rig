# Blender 图像转 3D 骨骼姿态插件（Pose2Rig）工程设计说明书

## 一、 项目概述与设计目标

### 1.1 项目背景与定位
在 3D 角色动画、二次元同人创作（VRM/MMD）、独立游戏开发（UE5/Unity）以及插画辅助领域，根据一张 2D 参考图在 Blender 中摆出还原度高的人体姿势（特别是包含透视角度与手指动作的复杂姿势）通常需要耗费熟练美术师 $15 \sim 30$ 分钟。

本项目旨在开发一款轻量、精准、开箱即用的商业级 Blender 插件 **Pose2Rig**：用户输入任意单人照片或二次元插画，插件在 $1$ 秒内提取 3D 全身骨骼旋转与手指姿态，自动创建匹配原图焦距的透视摄像机，并将动作一键重定向至主流角色骨架（Rigify、VRM/MMD、Auto-Rig Pro、UE5 Mannequin / Mixamo）。

### 1.2 核心设计指标（基于 RTX 3060 6GB 硬件基准）
* **显存安全性：** 峰值显存占用控制在 $\le 1.2\text{ GB}$，推理完成后 $100\%$ 释放显存，绝不与 Blender 视口渲染（Eevee / Cycles）争抢 VRAM 导致崩溃。
* **推理速度：** 单张图片端到端耗时（含人物检测、全身+手部 3D 姿态推理、Blender 骨骼映射）在 RTX 3060 上控制在 $0.4 \sim 0.8\text{ s}$ 以内，纯 CPU 兜底模式控制在 $\le 2.5\text{ s}$。
* **零环境污染：** 插件采用独立子进程（Worker）与 ONNX Runtime（FP16 半精度）架构，无需用户在 Blender 内安装庞大的 PyTorch 或编译 `chumpy` 等老旧依赖。

---

## 二、 现成开源实现参考与代码复用矩阵

为避免重复造轮子，本项目的四大核心技术环节均建立在已验证的开源仓库之上。开发时可直接将对应参考文件喂给 Coding Agent 进行移植与缝合：

| 所属模块 | 推荐参考开源仓库 | 核心复用文件 / 模块路径 | 直接复用的技术细节 |
| :--- | :--- | :--- | :--- |
| **1. 全身+透视相机推理** | `pixelite1201/CameraHMR`<br>(`bedlam2` 分支) | `demo.py`<br>`core/camerahmr_model.py` | 复用其基于边界框（BBox）估算全图相机焦距 $f_{\text{px}}$ 与三维平移向量 $\mathbf{T}_{\text{cam}}$ 的解算逻辑，以及 SMPL-X 参数输出结构。 |
| **2. 全身+手部一体备选** | `caizhongang/SMPLer-X` | `main/inference.py`<br>`common/utils/human_models.py` | 复用 `SMPLer-X-Large (ViT-L)` 的单图预处理（$256 \times 256$ 仿射裁切）及 55 关节轴角（Axis-Angle）提取管线。 |
| **3. 手指精度增强外挂** | `warmshao/WiLoR-mini`<br>`rolpotamias/WiLoR` | `wilor_mini/pipelines/` | 复用其手部 BBox 裁切、左右手镜像翻转归一化与 MANO $15 \times 3$ 轴角提取逻辑（原生支持 FP16）。 |
| **4. SMPL-X 转 Blender 骨架** | `zjucxh/smplx_blender_addon`<br>`Meshcapade/SMPL_blender_addon` | `smplx_blender_addon/__init__.py` (`set_pose_from_rodrigues`) | **极高价值：** 直接复用其将 SMPL-X 右手系罗德里格斯向量转换为 Blender 骨骼局部四元数（`rotation_quaternion`）的代码，省去坐标系调试。 |
| **5. 跨骨架自动重定向** | `Rokoko/rokoko-studio-live-blender` | `core/retargeting.py`<br>`core/bone_lists.py` | 复用主流骨架（Rigify / VRM / Mixamo）的自动命名匹配字典，以及基于编辑模式（Rest Pose）四元数差值的对齐算法。 |
| **6. AI 姿态后处理修正** | `squall01337/mixamo-llm-mocap` | `pipeline/retarget_smplx.py`<br>`docs/PITFALLS.md` | 参考其针对 SMPL-X 向外置骨架传递旋转时的前臂扭转（Forearm Roll）拆分、脊柱曲率控制与脚底贴地实现。 |
| **7. 合规权重下载器** | `toyxyz/toyxyz_RGBMocap` | `model_manager.py` | 借鉴其将插件代码与非商用模型权重解耦、通过面板一键从 HuggingFace/GitHub 拉取权重的合规商业模式。 |

---

## 三、 系统架构设计

### 3.1 为什么采用“前后端进程隔离 + 隐形中介骨架”架构？

在 Blender 插件开发中，直接在 Blender 内置 Python 主进程中调用深度学习模型并直接用数学公式覆写用户角色骨骼，会遇到两个致命工程问题：
1. **CUDA 上下文显存锁死：** 一旦在 Blender 主进程中初始化 GPU 推理会话，即使删除了模型变量，CUDA Runtime 仍会常驻占用 $800\text{ MB} \sim 1.5\text{ GB}$ 显存，直到 Blender 关闭。对于 6GB 显存用户，打开材质预览极易触发 `Out of Memory`。
2. **异构骨架坐标轴灾难：** 用户导入的二次元模型（VRM/MMD）或游戏模型，其骨骼局部轴向（Bone Roll）、初始姿态（T-Pose / A-Pose / 斜肩）千差万别，纯手写矩阵乘法极易导致手臂翻转 $180^\circ$。

因此，本系统设计为**三层解耦架构**：

```text
+-------------------------------------------------------------------------+
|                        [第 3 层：Blender UI 与交互层]                     |
|  3D Viewport N-Panel -> 选择参考图 & 目标角色骨架 -> 触发异步 Operator      |
+------------------------------------+------------------------------------+
                                     | 1. Subprocess 调用 (传递图片路径)
                                     v
+-------------------------------------------------------------------------+
|                  [第 1 层：独立推理 Worker 进程 (无 bpy 依赖)]             |
|  1. YOLOv8n (FP16 ONNX) 检测人物 BBox 并做 256x256 仿射变换裁切             |
|  2. SMPLer-X-Large / CameraHMR (FP16 ONNX) 推理全身 + 手指 + 相机参数     |
|  3. 写出标准 `pose_result.json` -> 进程退出，100% 释放 6GB 显卡显存         |
+------------------------------------+------------------------------------+
                                     | 2. 读取 JSON 数据契约
                                     v
+-------------------------------------------------------------------------+
|                    [第 2 层：Blender 场景构建与双层重定向层]               |
|  Step A: 相机对齐器 -> 创建透视相机，设置焦距 f_mm 与平移 T_cam，垫入背景图   |
|  Step B: 驱动内置隐形骨架 (Bridge SMPL-X Rig) -> 100% 零误差还原原图姿态    |
|  Step C: 挂载跨骨架 Copy Rotation 约束 (自动补偿 Rest Pose 四元数偏移)      |
|  Step D: 执行 Visual Keying 烘焙至用户角色 -> 应用肩膀/贴地微调滑块         |
+-------------------------------------------------------------------------+
```

---

## 四、 工程目录结构与模块职责划分

为了让 Coding Agent 在编写代码时保持清晰的模块边界，项目严格按以下目录组织：

```text
pose2rig_blender/
├── blender_manifest.toml          # Blender 4.2+ Extension 标准清单文件
├── __init__.py                    # 插件主入口：注册/注销 PropertyGroup、Operator、Panel
│
├── worker/                        # 【独立推理端】严禁在此目录下 import bpy
│   ├── infer_cli.py               # CLI 入口：接收 --img, --out, --device, --hand-refine
│   ├── detector.py                # YOLOv8n ONNX 人物检测与 BBox 扩展裁切逻辑
│   ├── estimator_onnx.py          # SMPLer-X / CameraHMR ONNX 会话推理与 Rodrigues 转换
│   ├── camera_solver.py           # 裁切框坐标反推全图焦距 f_mm 与 3D 相机位移解算
│   └── model_downloader.py        # 权重完整性校验与 HuggingFace 镜像源断点续传脚本
│
├── core/                          # 【Blender 核心算法端】纯 bpy 与 mathutils 逻辑
│   ├── schema_loader.py           # 解析并校验 pose_result.json
│   ├── camera_builder.py          # 在场景中生成匹配透视的 Camera 并配置 Background Image
│   ├── bridge_rig.py              # 加载并驱动隐藏的标准 SMPL-X 中介骨架 (Bridge Rig)
│   ├── retarget_engine.py         # 核心重定向引擎：Rest Pose 对齐、约束挂载与视觉烘焙
│   └── pose_modifiers.py          # 后处理修改器：脚底 Z=0 贴地、肩膀松弛、脊柱曲率、看向镜头
│
├── ui/                            # 【Blender 界面与状态层】
│   ├── properties.py              # 定义挂载在 bpy.types.Scene 上的插件属性与滑块回调
│   ├── operators.py               # 定义模态异步推理 Operator、烘焙 Operator、重置 Operator
│   ├── panels.py                  # 3D 视口侧边栏 (N-Panel -> Pose2Rig) 界面绘制
│   └── preferences.py             # 插件偏好设置：Python/ONNX 环境一键安装、模型管理面板
│
└── assets/                        # 【静态资源库】
    ├── bridge_smplx_rig.blend     # 仅包含标准 55 关节 SMPL-X 骨架（无蒙皮网格，体积 < 100KB）
    └── presets/                   # 跨骨架映射字典配置
        ├── rigify.json            # Blender 官方 Rigify ( FK 控制器与手指映射 )
        ├── vrm_mmd.json           # 二次元 VRM 标准骨骼与 MMD 日文/英文双语骨骼映射
        ├── auto_rig_pro.json      # Auto-Rig Pro (ARP) 控制器映射
        └── ue5_mixamo.json        # Unreal Engine 5 Mannequin 与 Mixamo 标准骨骼映射
```

---

## 五、 核心接口与数据契约规范（JSON Schemas）

### 5.1 推理端与 Blender 端通信契约：`pose_result.json`
`worker/infer_cli.py` 执行完毕后，必须输出严格符合以下格式的 JSON 文件。所有旋转量统一表示为 **局部坐标系下的轴角向量（Rodrigues Vector，$\boldsymbol{\omega} \in \mathbb{R}^3$）** 以及转换后的 **局部四元数 $[w, x, y, z]$**，方便 Blender 直接读取：

```json
{
  "version": "1.0",
  "meta": {
    "image_path": "D:/refs/anime_jump.png",
    "image_width": 1200,
    "image_height": 1600,
    "bbox_xyxy": [180.5, 110.0, 1020.0, 1510.0],
    "inference_time_ms": 342
  },
  "camera": {
    "sensor_width_mm": 36.0,
    "focal_length_mm": 48.25,
    "cam_translation_blender": [0.042, -2.680, 0.115],
    "cam_rotation_euler": [1.5708, 0.0, 0.0]
  },
  "smplx_pose": {
    "global_orient": [0.12, -0.05, 0.01],
    "joints": {
      "pelvis":      { "quat_wxyz": [0.998, 0.052, -0.021, 0.010] },
      "left_hip":    { "quat_wxyz": [0.965, -0.251, 0.043, -0.061] },
      "right_hip":   { "quat_wxyz": [0.981, 0.182, -0.032, 0.045] },
      "spine1":      { "quat_wxyz": [0.995, 0.088, 0.012, -0.005] },
      "spine2":      { "quat_wxyz": [0.997, 0.064, 0.008, -0.002] },
      "spine3":      { "quat_wxyz": [0.999, 0.031, 0.004, -0.001] },
      "neck":        { "quat_wxyz": [0.991, -0.112, 0.065, 0.021] },
      "head":        { "quat_wxyz": [0.988, -0.095, -0.114, 0.032] },
      "left_collar": { "quat_wxyz": [0.994, 0.021, -0.085, 0.062] },
      "right_collar":{ "quat_wxyz": [0.993, 0.019, 0.091, -0.068] },
      "left_shoulder":  { "quat_wxyz": [0.852, 0.310, -0.285, 0.312] },
      "right_shoulder": { "quat_wxyz": [0.871, 0.295, 0.264, -0.290] },
      "left_elbow":  { "quat_wxyz": [0.912, 0.045, 0.405, 0.032] },
      "right_elbow": { "quat_wxyz": [0.895, 0.038, -0.442, -0.028] },
      "left_wrist":  { "quat_wxyz": [0.992, -0.081, 0.092, 0.015] },
      "right_wrist": { "quat_wxyz": [0.990, -0.075, -0.110, -0.018] },
      "left_knee":   { "quat_wxyz": [0.945, 0.325, 0.012, -0.008] },
      "right_knee":  { "quat_wxyz": [0.960, 0.278, -0.015, 0.010] },
      "left_ankle":  { "quat_wxyz": [0.985, -0.170, 0.020, 0.005] },
      "right_ankle": { "quat_wxyz": [0.988, -0.152, -0.018, -0.004] }
    },
    "hands": {
      "left_index1": { "quat_wxyz": [0.951, 0.012, 0.045, 0.305] },
      "left_index2": { "quat_wxyz": [0.920, 0.000, 0.000, 0.391] },
      "left_index3": { "quat_wxyz": [0.965, 0.000, 0.000, 0.262] }
    }
  }
}
```

### 5.2 骨骼重定向预设字典契约：`assets/presets/*.json`
为了支持一键适配多种角色骨架，每个预设文件定义了从 `Bridge SMPL-X Rig` 标准关节名到目标骨架候选名称列表（按匹配优先级排序）的映射：

```json
{
  "preset_name": "VRM / MMD / General Anime",
  "root_bone": ["hips", "J_Bip_C_Hips", "下半身", "pelvis", "Root"],
  "bone_mapping": {
    "pelvis":         ["hips", "J_Bip_C_Hips", "下半身"],
    "spine1":         ["spine", "J_Bip_C_Spine", "上半身"],
    "spine2":         ["chest", "J_Bip_C_Chest", "上半身2"],
    "spine3":         ["upperChest", "J_Bip_C_UpperChest"],
    "neck":           ["neck", "J_Bip_C_Neck", "首"],
    "head":           ["head", "J_Bip_C_Head", "頭"],
    "left_collar":    ["leftShoulder", "J_Bip_L_Shoulder", "左肩"],
    "left_shoulder":  ["leftUpperArm", "J_Bip_L_UpperArm", "左腕"],
    "left_elbow":     ["leftLowerArm", "J_Bip_L_LowerArm", "左ひじ"],
    "left_wrist":     ["leftHand", "J_Bip_L_Hand", "左手首"],
    "left_hip":       ["leftUpperLeg", "J_Bip_L_UpperLeg", "左足"],
    "left_knee":      ["leftLowerLeg", "J_Bip_L_LowerLeg", "左ひざ"],
    "left_ankle":     ["leftFoot", "J_Bip_L_Foot", "左足首"],
    "left_foot":      ["leftToes", "J_Bip_L_ToeBase", "左つま先"],
    "left_thumb1":    ["leftThumbProximal", "J_Bip_L_Thumb1", "左親指０"],
    "left_thumb2":    ["leftThumbIntermediate", "J_Bip_L_Thumb2", "左親指１"],
    "left_thumb3":    ["leftThumbDistal", "J_Bip_L_Thumb3", "左親指２"],
    "left_index1":    ["leftIndexProximal", "J_Bip_L_Index1", "左人指１"],
    "left_index2":    ["leftIndexIntermediate", "J_Bip_L_Index2", "左人指２"],
    "left_index3":    ["leftIndexDistal", "J_Bip_L_Index3", "左人指３"]
  }
}
```

---

## 六、 核心算法与数学转换规范

在让 Coding Agent 编写 `worker/camera_solver.py` 与 `core/retarget_engine.py` 时，必须严格遵循以下数学规范：

### 6.1 局部裁切框（Crop BBox）反推全图透视相机
视觉模型是在裁切后的正方形局部框（中心为 $(c_x, c_y)$，边长为 $b$）上预测弱透视参数 $\mathbf{cam}_{\text{crop}} = (s, t_x, t_y)$ 的。若直接将该平移用于原图（分辨率 $W \times H$），当人物不在画面正中央时，3D 模型会严重偏离背景图人物位置。

设全图等效焦距（像素单位）为 $f_{\text{px}}$（若使用 CameraHMR 则由网络直接输出；若使用 SMPLer-X 则取经验公式 $f_{\text{px}} = \sqrt{W^2 + H^2}$），则全图相机相对于人物根节点（Pelvis）的三维平移向量 $\mathbf{T}_{\text{full}} = (T_X, T_Y, T_Z)$ 计算如下：

$$T_Z = \frac{2 \cdot f_{\text{px}}}{s \cdot b}$$

$$T_X = t_x + \frac{2 \cdot \left( c_x - \frac{W}{2} \right)}{s \cdot b}, \quad T_Y = t_y + \frac{2 \cdot \left( c_y - \frac{H}{2} \right)}{s \cdot b}$$

将相机坐标系（$X$ 向右，$Y$ 向下，$Z$ 指向画面内）转换至 Blender 世界坐标系（$X$ 向右，$Y$ 向深处，$Z$ 向上，且角色 Pelvis 位于世界原点附近）：
* **Blender 相机焦距（毫米）：** 设传感器宽度 $S_w = 36\text{ mm}$，当 $W \ge H$ 时：
  $$f_{\text{mm}} = \frac{f_{\text{px}} \cdot S_w}{W}$$
* **Blender 相机位置与旋转：**
  相机欧拉角固定设为 $(\frac{\pi}{2}, 0, 0)$（正对 $+Y$ 方向），相机世界坐标 $\mathbf{P}_{\text{cam}}$ 设为：
  $$\mathbf{P}_{\text{cam}} = \begin{bmatrix} -T_X \\ -T_Z \\ T_Y \end{bmatrix}$$

### 6.2 罗德里格斯向量转 Blender SMPL-X 骨架四元数
SMPL-X 原始骨架局部坐标系为：$+X$ 向左，$+Y$ 向上，$+Z$ 向前；而在 Blender 内置的 `bridge_smplx_rig.blend` 中，骨骼轴向沿着 $+Y$ 延伸。
对于任意关节输出的轴角向量 $\boldsymbol{\omega} = (\omega_x, \omega_y, \omega_z)$，令 $\theta = \|\boldsymbol{\omega}\|_2$：

$$\mathbf{q}_{\text{smplx}} = \begin{cases} (1, 0, 0, 0), & \text{if } \theta < 10^{-8} \\ \left( \cos\frac{\theta}{2}, \; \frac{\omega_x}{\theta}\sin\frac{\theta}{2}, \; \frac{\omega_y}{\theta}\sin\frac{\theta}{2}, \; \frac{\omega_z}{\theta}\sin\frac{\theta}{2} \right), & \text{otherwise} \end{cases}$$

直接复用 `smplx_blender_addon` 中的轴向修正逻辑，将骨骼置为 `QUATERNION` 旋转模式并写入 `pose_bone.rotation_quaternion`。

### 6.3 跨骨架初始姿态补偿算法（Rest Pose Offset Matrix）
设中介骨架（Source Rig $S$）与用户角色骨架（Target Rig $T$）的某对匹配骨骼分别为 $B_S$ 与 $B_T$。
1. **记录初始静息偏移（在姿态归零状态下计算一次）：**
   读取两根骨骼在各自 Armature 世界空间下的静息旋转矩阵（包含 Armature Object 变换）：
   $$\mathbf{R}_{S,\text{rest}} = (\mathbf{M}_{\text{obj},S} \cdot \mathbf{B}_{S,\text{matrix\_local}}).\text{to\_3x3}()$$
   $$\mathbf{R}_{T,\text{rest}} = (\mathbf{M}_{\text{obj},T} \cdot \mathbf{B}_{T,\text{matrix\_local}}).\text{to\_3x3}()$$
   计算静息姿态偏移矩阵：
   $$\mathbf{\Delta R}_{\text{offset}} = \mathbf{R}_{S,\text{rest}}^{-1} \cdot \mathbf{R}_{T,\text{rest}}$$

2. **姿态传递（按从父骨骼到子骨骼的拓扑序遍历，避免多次调用 `context.view_layer.update()`）：**
   当中介骨骼 $B_S$ 获得推理后的世界空间旋转矩阵 $\mathbf{R}_{S,\text{posed}}$ 时，目标骨骼 $B_T$ 应达到的世界空间旋转矩阵为：
   $$\mathbf{R}_{T,\text{target\_world}} = \mathbf{R}_{S,\text{posed}} \cdot \mathbf{\Delta R}_{\text{offset}}$$
   将其转换为目标骨骼在 Armature 对象空间下的姿态矩阵 `pose_bone.matrix`，直接赋值即可一步到位完成跨 T-Pose / A-Pose 的精准映射。

### 6.4 四大商业级后处理修正算法（`core/pose_modifiers.py`）
为了解决 AI 识别插画时的常见通病，在骨骼映射完成后执行以下实时修正：

1. **耸肩松弛修正（Shoulder Relax，滑块参数 $\alpha \in [0, 1]$）：**
   插画与动漫角色常因透视导致 AI 预测的锁骨（`left_collar` / `right_collar`）过度上抬。对锁骨的局部四元数 $\mathbf{q}_{\text{collar}}$ 与单位四元数 $\mathbf{q}_{\text{identity}} = (1,0,0,0)$ 做球面线性插值（Slerp）：
   $$\mathbf{q}_{\text{collar\_new}} = \text{Slerp}\left(\mathbf{q}_{\text{collar}}, \; \mathbf{q}_{\text{identity}}, \; 0.6 \cdot \alpha\right)$$
2. **脊柱表现力缩放（Spine Curvature，滑块参数 $\beta \in [0.5, 1.5]$）：**
   对 `spine1`、`spine2`、`spine3` 的局部旋转角乘上比例系数 $\beta$，一键强化或平缓二次元角色的“S 型腰线”。
3. **自动脚底贴地（Snap to Ground Z=0）：**
   遍历目标骨架的左右脚踝（`ankle`）与脚尖（`toe`）骨骼末端（`tail`）的世界坐标，找出最低高度：
   $$z_{\min} = \min_{b \in \{\text{feet}\}} \left( \mathbf{M}_{\text{obj},T} \cdot b.\text{tail} \right)_z$$
   将根骨骼（`hips` / `pelvis`）的世界空间 $Z$ 坐标平移 $-z_{\min}$，使角色稳稳踩在地面网格上。
4. **前臂扭转分摊（Forearm Twist Split）：**
   对于包含前臂扭转骨骼（Twist Bone）的精细二次元或游戏模型，将手腕（`wrist`）绕前臂延伸轴（$Y$ 轴）的扭转分量提取出 $50\%$ 分配给前臂或 Twist 骨骼，消除手腕处的“糖果纸拧麻花”塌陷。

---

## 七、 UI 交互设计与商业化版本切分

### 7.1 3D 视口侧边栏（N-Panel）布局规范
插件面板保持极简三步操作，拒绝繁琐参数：

```text
+---------------------------------------------------+
| [v] Pose2Rig (AI Image to 3D Pose)                |
+---------------------------------------------------+
| 1. Reference Image                                |
|   +-------------------------------------------+   |
|   |        [ 图片缩略图预览区 (Preview) ]      |   |
|   +-------------------------------------------+   |
|   [ Open Image... ]               [Paste Clipboard]|
|   [x] Match Perspective Camera    Opacity: [0.50] |
+---------------------------------------------------+
| 2. Target Character Rig                           |
|   Armature: [ 吸管选择：Character_Armature   v ]   |
|   Preset:   [ Auto-Detect (VRM Detected)     v ]   |
|   [x] Include Fingers (30 Joints)                 |
+---------------------------------------------------+
| 3. Generate & Pose Polish                         |
|   +-------------------------------------------+   |
|   |        >>  GENERATE 3D POSE (1s)  <<      |   |
|   +-------------------------------------------+   |
|   Shoulder Relax:   [=======|-------] 0.45        |
|   Spine Curvature:  [---------|=====] 1.15        |
|   [ Snap Feet to Ground ]   [ Head Look at Cam ]  |
|   [ Bake to Keyframe ]      [ Save to Pose Lib ]  |
+---------------------------------------------------+
```

### 7.2 开源引流版（Free）与付费专业版（Pro）边界设计
遵循“几百 Star 高转化变现”原则，通过同一个代码库构建两个发行包：

| 功能特性 | GitHub 开源版 (Free) | 商业完整版 (Pro - \$29 / ¥68) | 设计意图 |
| :--- | :--- | :--- | :--- |
| **全身 22 关节躯干识别** | 支持 | 支持 | 让免费用户验证核心准确度，在社区自发传播 |
| **内置 SMPL-X 骨架与 Rigify 映射** | 支持 | 支持 | 满足基础极客用户的测试需求 |
| **VRM / MMD / ARP / UE5 一键预设** | 需手动配置字典 | **内置全自动识别与映射** | 精准切中二次元创作者与独游开发者的“嫌麻烦”痛点 |
| **30 关节精细手指姿态识别** | 不包含 | **完整支持 (含 WiLoR 增强)** | 掰手指是 Blender 最耗时的痛点，付费转化率极高 |
| **透视相机焦距对齐 + 背景垫图** | 不包含 | **一键生成对齐相机** | 拍演示视频最吸睛的视觉爽点 |
| **姿态微调滑块 (耸肩/腰线/贴地)** | 不包含 | **实时交互滑块** | 解决最后 $10\%$ 的人类审美调优 |
| **环境与模型安装方式** | 需自行配 Python 环境 | **内置一键免配置加速引擎包** | 为不懂命令行的小白美术省下三天配环境时间 |

---

## 八、 面向 Coding Agent 的四阶段实施路线与 Prompt 模板

开发过程严禁让 Agent 一次性生成所有代码。请按照以下 4 个阶段，依次将对应的 Prompt 复制给你的 Coding Agent，每跑通并验收一个阶段，再进入下一阶段：

### 阶段 1：构建独立推理 Worker 并验证 3060 显存与耗时
**验收目标：** 在终端运行 `python worker/infer_cli.py --img test.jpg --out result.json`，峰值显存 $\le 1.2\text{ GB}$，耗时 $< 0.8\text{ s}$，输出合法的 `result.json`。

> **复制给 Coding Agent 的指令（Stage 1 Prompt）：**
> 请阅读项目根目录下的 `DESIGN_SPEC.md`。现在我们只开发 **第 1 层：`worker/` 独立推理模块**（严禁在此模块引入 `bpy`）。
> 1. 请创建 `worker/` 目录及 `requirements.txt`、`detector.py`、`camera_solver.py`、`estimator_onnx.py`、`infer_cli.py`。
> 2. 参考 `pixelite1201/CameraHMR` 或 `caizhongang/SMPLer-X` 的单图推理预处理逻辑，实现：
>    - 使用轻量级人体检测框出人物主体的 `bbox_xyxy`；
>    - 将裁切后的 $256 \times 256$ 图像输入姿态估计模型（开启 FP16 半精度推理以适配我的 RTX 3060 6GB 显卡）；
>    - 按照 `DESIGN_SPEC.md` 第六节 6.1 与 6.2 的公式，计算全图透视相机参数（`focal_length_mm` 与 `cam_translation_blender`），并将全身 22 个关节与双手 30 个关节的轴角转换为四元数 `quat_wxyz`；
>    - 严格按照 `DESIGN_SPEC.md` 第五节 5.1 的 JSON Schema 输出 `pose_result.json`，并在控制台打印推理耗时与 GPU 峰值显存占用。
> 3. 请先编写一个测试脚本验证整条 CLI 管道可独立跑通。

---

### 阶段 2：Blender 透视相机对齐与隐形中介骨架驱动
**验收目标：** 在 Blender 中运行脚本读取阶段 1 生成的 `result.json`，按下小键盘 `0` 进入生成的摄像机视角，生成的 SMPL-X 骨架与背景图片中的人物动作和透视完全重合。

> **复制给 Coding Agent 的指令（Stage 2 Prompt）：**
> 阶段 1 的 `pose_result.json` 已经验证通过。现在请根据 `DESIGN_SPEC.md` 开发 **`core/schema_loader.py`、`core/camera_builder.py` 和 `core/bridge_rig.py`**：
> 1. 参考 `zjucxh/smplx_blender_addon` 的骨骼坐标转换实现，编写一个能在 Blender 中根据 SMPL-X 标准关节父子层级动态生成（或从资产加载）标准中介骨架 `Bridge_SMPLX_Rig` 的函数，并将 JSON 中的 `quat_wxyz` 精确应用到对应 `pose.bones` 上。
> 2. 编写 `camera_builder.py`：根据 JSON 中的 `camera` 字段，在场景中创建或更新名为 `Pose2Rig_Camera` 的透视摄像机，设置对应的 `lens`（焦距）、`sensor_width`、位置与旋转，并自动将输入图片挂载为该摄像机的 `background_images`（透明度设为 0.5，置于前景 Front）。
> 3. 编写一个可在 Blender Text Editor 中直接运行的测试入口脚本 `test_stage2_in_blender.py`。

---

### 阶段 3：跨骨架零扭曲重定向与微调修改器
**验收目标：** 导入一个 VRM 二次元角色和一个 Rigify 角色，执行重定向后四肢与手指不发生麻花翻转，拖动“肩膀松弛”和“自动贴地”滑块能实时生效。

> **复制给 Coding Agent 的指令（Stage 3 Prompt）：**
> 阶段 2 的中介骨架与相机对齐已完全吻合。现在请根据 `DESIGN_SPEC.md` 第五节 5.2 和第六节 6.3、6.4，开发 **`core/retarget_engine.py`、`core/pose_modifiers.py` 以及 `assets/presets/` 下的预设 JSON**：
> 1. 生成 `vrm_mmd.json`、`rigify.json`、`ue5_mixamo.json` 三个完整骨骼映射表（包含躯干、四肢与五指三节关节）。
> 2. 在 `retarget_engine.py` 中实现基于编辑模式静息姿态偏移矩阵（$\mathbf{\Delta R}_{\text{offset}} = \mathbf{R}_{S,\text{rest}}^{-1} \cdot \mathbf{R}_{T,\text{rest}}$）的世界空间旋转传递算法。按骨骼从根到叶的拓扑顺序单次遍历更新矩阵，避免重复调用 `view_layer.update()` 造成卡顿。
> 3. 在 `pose_modifiers.py` 中实现四个后处理函数：`apply_shoulder_relax(armature, factor)`、`apply_spine_curvature(armature, factor)`、`snap_feet_to_ground(armature)` 和 `align_head_to_camera(armature, camera)`。

---

### 阶段 4：Blender 4.2+ N-Panel 界面封装与非阻塞调用
**验收目标：** 作为标准插件安装进 Blender，点击按钮时界面不卡死，推理子进程结束后立即销毁显存并完成角色摆姿。

> **复制给 Coding Agent 的指令（Stage 4 Prompt）：**
> 核心算法已全部调通。现在请根据 `DESIGN_SPEC.md` 第七节开发 **`ui/` 目录、`__init__.py` 以及 `blender_manifest.toml`**：
> 1. 使用 `subprocess.Popen` 结合 Blender 的 `Modal Timer Operator` 实现非阻塞异步调用 `worker/infer_cli.py`，在推理期间于状态栏显示进度提示，子进程结束后立即触发 `bridge_rig` -> `retarget_engine` -> `pose_modifiers` 流水线。
> 2. 按照 `DESIGN_SPEC.md` 7.1 节的布局绘制 3D 视口侧边栏 `Pose2Rig` 面板，为 `Shoulder Relax` 和 `Spine Curvature` 滑块绑定实时 `update` 回调。
> 3. 编写 `ui/preferences.py`，提供外部 Python 解释器路径配置（或内置虚拟环境检测）以及模型权重状态检查按钮。
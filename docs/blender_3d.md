# Blender 图像转 3D 骨骼姿态插件：开源复用调研与工程设计方案

> **项目定位：** 面向二次元创作者（VRM/MMD）、独立游戏开发者（UE5/Mixamo）与 Blender 角色画师（Rigify/Auto-Rig Pro）的**“单图 1 秒精准还原 3D 骨骼姿势 + 透视相机自动对齐”**轻量级商业插件。
> **目标硬件基准：** NVIDIA RTX 3060 (6GB VRAM) 流畅运行，峰值显存增量控制在 $\le 1.2\text{ GB}$，单图端到端耗时 $\le 0.8\text{ s}$。

---

## 一、 核心结论：如何避免 80% 的重复造轮子工作？

要把“一张 2D 图片”变成“Blender 里任意角色身上的精准姿势”，完整链路分为 4 个模块。调研表明，**前 3 个模块在 GitHub 上均有成熟的开源代码可直接参考或移植**，你只需要让手头的 Coding Agent 做“缝合、轻量化与交互封装”：

1. **视觉推理层（2D 图 $\rightarrow$ SMPL-X 姿态参数 + 相机参数）：** 无需自己训练或手写网络结构，直接复用 **CameraHMR (SMPL-X 版)** 或 **SMPLer-X** 的推理管线，并结合 **WiLoR-mini** 强化手指精度。
2. **Blender 基准骨架生成层（SMPL-X 参数 $\rightarrow$ Blender 隐形中介骨架）：** 直接参考 **zjucxh/smplx_blender_addon** 与 **Meshcapade/SMPL_blender_addon** 中现成的罗德里格斯向量（Rodrigues Vector）转 Blender 四元数与坐标系修正代码。
3. **跨骨架重定向层（SMPL-X 中介骨架 $\rightarrow$ Rigify / VRM / Mixamo）：** 直接复用 **Rokoko Studio Live for Blender**（开源）的骨骼映射字典与 Rest Pose 偏移补偿逻辑，以及 **squall01337/mixamo-llm-mocap** 中的 SMPL-X 局部旋转传递算法。
4. **你真正需要打磨的差异化壁垒（占 20% 工作量）：**
   * 将笨重的 PyTorch 依赖裁剪为免配置的 **ONNX Runtime (FP16)** 独立推理包；
   * 一键在 Blender 中生成**匹配原图焦距的透视相机**并垫入半透明参考图；
   * 提供针对二次元夸张身材比例的 **微调滑块（肩膀放松、脊柱曲率、脚底贴地 IK）**。

---

## 二、 现成开源仓库深度盘点（直接抄作业清单）

### 1. 视觉识别端：单图恢复 3D 人体与相机透视

| 开源仓库 | GitHub 地址 | 核心优势与可复用代码 | 在本插件中的角色 |
| :--- | :--- | :--- | :--- |
| **CameraHMR** | `pixelite1201/CameraHMR` | 专门解决**大透视/广角/俯仰拍变形**问题，直接预测相机内参焦距 $f$；其最新 `bedlam2` 分支已原生支持 **SMPL-X** 全身参数输出。 | **核心底座首选**：复用其 `demo.py` 中的相机透视解算与 Crop 预处理逻辑。 |
| **SMPLer-X** | `caizhongang/SMPLer-X` | 原生全身一体化模型（身体 + 双手 MANO + 面部），提供 S/B/L/H 四种规格权重。其中 `ViT-L` 规格在 6GB 显卡上性价比极高。 | **备选/全身底座**：复用其单图推理脚本与 SMPL-X 55 关节旋转输出格式。 |
| **WiLoR / WiLoR-mini** | `rolpotamias/WiLoR`<br>`warmshao/WiLoR-mini` | CVPR 2025 手部三维重建 SOTA，原生支持 `--fast`（FP16 半精度推理），`WiLoR-mini` 已封装为单条 `pip` 命令即可调用的轻量包。 | **手指精度外挂**：当全身模型手指识别不够准时，裁切手部区域用它做二次精细覆盖。 |

### 2. SMPL-X 转换与 Blender 骨骼驱动端

很多人自己写代码把 SMPL 旋转矩阵往 Blender 里导时，会被右手坐标系转换（Y-up 转 Z-up）和骨骼局部轴向折磨得死去活来。以下仓库已经彻底解决了这个问题：

| 开源仓库 | GitHub 地址 | 可直接提取的核心代码文件/逻辑 | 避坑价值 |
| :--- | :--- | :--- | :--- |
| **SMPL-X Blender Add-on** | `zjucxh/smplx_blender_addon` | 提取其 `load_pose` 相关函数：包含如何将 55 个关节的轴角向量（Rodrigues notation，$\theta \in \mathbb{R}^{55 \times 3}$）精确转换为 Blender `pose.bones[name].rotation_quaternion` 的完整实现。 | **省去 3 天数学调试**：直接拿到 100% 正确的 SMPL-X $\rightarrow$ Blender 骨骼坐标变换矩阵。 |
| **Meshcapade Blender Add-on** | `Meshcapade/SMPL_blender_addon` | 包含读取 `.npz` / `.json` 姿态数据、处理根节点（Pelvis）全局位移与旋转修正的标准写法。 | 提供现成的轻量级无蒙皮 SMPL-X 标准骨架层级结构参考。 |

### 3. 跨骨骼重定向（Retargeting）与工作流参考

把姿势赋给标准 SMPL 骨架只是第一步，用户最终需要把姿势贴到自己的 **Rigify、VRM（二次元模型）、Auto-Rig Pro 或 UE5 小白人** 上：

| 开源仓库 | GitHub 地址 | 可直接复用的模块 | 核心借鉴点 |
| :--- | :--- | :--- | :--- |
| **Rokoko Studio Live for Blender** | `Rokoko/rokoko-studio-live-blender` | `retargeting.py`、`bone_lists.py`、`operators/retarget.py` | **行业级重定向标杆**：内置了自动识别 Rigify、Mixamo、VRM、UE 等主流骨骼命名的字典，以及處理 T-Pose 与 A-Pose 初始姿态差异（Rest Pose Alignment）的完整矩阵计算代码。 |
| **mixamo-llm-mocap** | `squall01337/mixamo-llm-mocap` | `pipeline/retarget_smplx.py`、`pipeline/bl_motion.py`、`docs/PITFALLS.md` | 专门针对 AI 提取的 SMPL-X 参数向目标角色骨架传递正向动力学（FK）旋转（包含前臂扭转 Forearm Roll、脊柱曲率、脚尖朝向修正），且专门面向 AI Agent 辅助开发编写了踩坑文档。 |
| **vid2anim** | `mehulcode12/vid2anim` | 通用重定向模块与 Blender 插件封装结构 | 实现了轻量级 CPU/GPU 兼容的姿态提取与向 Mixamo/VRM/Rigify/UE5 的一键重定向流程。 |
| **toyxyz_RGBMocap** | `toyxyz/toyxyz_RGBMocap` | `Model Manager` 权重按需下载机制与低显存管理策略 | **反面教材与商业启发**：该软件完整安装高达 $67.9\text{ GB}$，极其笨重；但它通过内置 `Model Manager` 让用户自行一键拉取非商用模型权重的合规设计，非常值得我们在商业化时直接照搬。 |

---

## 三、 针对 RTX 3060 (6GB) 的技术架构与数学管线

### 1. 显存安全架构：前后端分离（避免与 Blender 视口抢显存）

在 6GB 显存环境下，绝不能在 Blender 内置的 Python 主线程里常驻庞大的 PyTorch 模型。我们采用**“轻量 Worker 进程 + ONNX Runtime FP16”**架构：

```
[Blender 4.2+ 插件前端 (bpy)]
  ├── 用户拖入参考图 (.png/.jpg) & 选择目标角色骨架 (Rigify / VRM / Mixamo)
  ├── 点击 "1-Click Pose" 按钮
  │
  ▼ (通过本地 Subprocess / Socket 发送图片路径，耗时 < 5ms)
[独立推理环境 (ONNX Runtime GPU - FP16)]
  ├── 1. YOLOv8n-pose / BBox 检测人物框并裁切为 256x256 (显存 ~40MB, 耗时 10ms)
  ├── 2. CameraHMR / SMPLer-X-Large (FP16 ONNX) 推理全身 + 相机焦距 (显存 ~850MB, 耗时 200ms)
  ├── 3. (可选) WiLoR-mini (FP16) 推理双手精细 MANO 姿态 (显存 ~250MB, 耗时 80ms)
  ├── 4. 输出结构化 `pose_result.json` 并立即释放显存缓存
  │
  ▼ (Blender 读取 JSON 并执行纯数学矩阵映射，耗时 < 30ms)
[Blender 场景自动构建与重定向引擎]
  ├── 自动创建/匹配透视相机 (对齐焦距与平移向量，垫入半透明原图)
  ├── 驱动隐藏的 SMPL-X 中介骨架 (Proxy Rig)
  └── 跨骨架四元数重定向 → 目标角色骨架 + 脚底 Z=0 贴地修正
```

### 2. 三大核心数学转换（供 Coding Agent 编写代码时的规范公式）

在让 Agent 编写 `retarget_engine.py` 时，直接将以下三个数学约束作为 Prompt 规范喂给它，可一次性避免骨骼扭曲：

#### (1) 罗德里格斯向量（轴角）转 Blender 局部四元数
视觉模型输出的姿态参数为轴角向量 $\boldsymbol{\omega} = (\omega_x, \omega_y, \omega_z) \in \mathbb{R}^3$，旋转角为 $\theta = \|\boldsymbol{\omega}\|_2$，单位旋转轴为 $\mathbf{u} = \boldsymbol{\omega} / \theta$。
由于 SMPL 采用右手系（通常 $Y$ 轴向上或相机系 $Y$ 轴向下），而 Blender 骨骼局部坐标系强制以 $Y$ 轴作为骨骼延伸方向（Bone Roll），转换后的四元数 $\mathbf{q}_{\text{blender}}$ 需经过坐标系置换算子：

$$\mathbf{q}_{\text{raw}} = \left( \cos\frac{\theta}{2}, \; u_x\sin\frac{\theta}{2}, \; u_y\sin\frac{\theta}{2}, \; u_z\sin\frac{\theta}{2} \right)$$

$$\mathbf{M}_{\text{pose\_basis}} = \mathbf{C}_{\text{axis}} \cdot \text{QuatToMat}(\mathbf{q}_{\text{raw}}) \cdot \mathbf{C}_{\text{axis}}^{-1}$$

*注：具体置换矩阵 $\mathbf{C}_{\text{axis}}$ 直接复制 `zjucxh/smplx_blender_addon` 中的 `rodrigues_to_quat` 函数即可，无需重新推导。*

#### (2) 跨骨架初始姿态补偿（Rest Pose Offset Compensation）
当把隐藏的 SMPL-X 中介骨架（源骨架 $S$，标准 T-Pose）的动作映射到用户的二次元 VRM 或 Rigify 骨架（目标骨架 $T$，可能是 A-Pose 或斜肩）时，设源骨骼与目标骨骼在各自编辑模式（Rest Pose）下的世界空间旋转矩阵分别为 $\mathbf{R}_{S,\text{rest}}$ 和 $\mathbf{R}_{T,\text{rest}}$。
当源骨骼在姿态模式下产生世界空间旋转 $\mathbf{R}_{S,\text{pose}}$ 时，目标骨骼的目标世界旋转 $\mathbf{R}_{T,\text{pose}}$ 为：

$$\mathbf{R}_{T,\text{pose}} = \mathbf{R}_{S,\text{pose}} \cdot \left( \mathbf{R}_{S,\text{rest}}^{-1} \cdot \mathbf{R}_{T,\text{rest}} \right)$$

随后转换为 Blender 目标骨骼的局部基矩阵（`matrix_basis`）：

$$\mathbf{M}_{T,\text{basis}} = \left( \mathbf{M}_{T,\text{parent\_pose}} \cdot \mathbf{M}_{T,\text{local\_rest}} \right)^{-1} \cdot \mathbf{R}_{T,\text{pose}}$$

#### (3) 透视相机焦距与位置自动对齐
CameraHMR 会输出預測的弱透视/透视相机参数 $\mathbf{cam} = (s, t_x, t_y)$ 以及焦距 $f_{\text{px}}$（像素单位）。设输入原图分辨率为 $W \times H$，Blender 相机默认传感器宽度 $S_w = 36\text{ mm}$，则 Blender 相机的焦距 $f_{\text{mm}}$ 与相机相对人物根节点（Pelvis）的三维平移向量 $\mathbf{T}_{\text{cam}}$ 计算如下：

$$f_{\text{mm}} = \frac{f_{\text{px}} \cdot S_w}{\max(W, H)}$$

$$Z_{\text{depth}} = \frac{2 \cdot f_{\text{px}}}{s \cdot \max(W, H)}, \quad \mathbf{T}_{\text{cam}} = \begin{bmatrix} t_x \\ -Z_{\text{depth}} \\ -t_y \end{bmatrix}$$

这能让生成的 3D 角色在进入相机视角（Numpad `0`）时，与背景参考图达到像素级重合。

---

## 四、 商业化合规与打包策略（避开开源协议雷区）

很多个人开发者把开源 AI 模型做成插件去卖时，最容易踩的坑是**直接把非商用（CC-BY-NC）的模型权重文件（`.ckpt` / `.onnx`）打包进付费 ZIP 安装包里售卖**，这会导致商品被平台下架甚至引发版权纠纷。

**标准合规商业模式（参考 ComfyUI 与 RGBMocap 的成熟做法）：**

1. **插件本体代码与权重彻底解耦：**
   你售卖的 ZIP 包（仅几 MB 大小）只包含你编写的 **Blender UI 面板、透视相机对齐工具、跨骨骼重定向预设、微调滑块算法以及环境自动配置脚本**。
2. **内置一键式 `Model Manager`（模型下载器）：**
   用户在 Blender 插件偏好设置里点击 `Download AI Engine & Weights`，由脚本自动从 HuggingFace / GitHub 官方源拉取预转换好的推理权重到本地用户目录（`AppData/Roaming/Blender Foundation/...`）。这样你在法律上售卖的是**“纯工作流与重定向软件工具”**，而非倒卖学术模型权重。
3. **注意 Rokoko 代码的 GPL 传染性：**
   Blender 插件只要调用了 `import bpy`，其前端胶水代码天然遵循 GPL 协议（这也是所有 Blender 付费插件在 Blender Market / Gumroad 上正常售卖的通行规则）。但你的**核心姿态优化与推理转换模块**可以通过独立 Python 包或编译模块调用，保持技术壁垒。

---

## 五、 面向 Coding Agent 的 7 天开发执行路线图

你可以直接将以下 4 个阶段作为任务看板，每天让你的 Agent 完成一个独立闭环：

### 阶段 1：脱离 Blender 跑通独立推理脚本（第 1～2 天）
* **操作：** 拉取 `pixelite1201/CameraHMR`（或 `caizhongang/SMPLer-X`）与 `warmshao/WiLoR-mini`。
* **给 Agent 的指令：**
  > “帮我写一个独立的 `infer_single_image.py` 脚本。输入一张单人动作或动漫插画图片路径，调用模型提取 SMPL-X 的 `global_orient` (1x3)、`body_pose` (21x3)、`left_hand_pose` (15x3)、`right_hand_pose` (15x3) 以及相机参数 `cam_t` 和 `focal_length`，统一保存为结构化的 `pose_output.json`。同时将模型以 FP16 半精度运行，打印在 RTX 3060 上的峰值显存占用与耗时。”

### 阶段 2：在 Blender 内复现标准 SMPL-X 骨架与透视相机（第 3 天）
* **操作：** 下载 `zjucxh/smplx_blender_addon` 的源码作为 Agent 的上下文参考。
* **给 Agent 的指令：**
  > “参考 `smplx_blender_addon` 中的坐标轴转换与罗德里格斯公式，帮我写一段 Blender Python (`bpy`) 脚本：读取阶段 1 生成的 `pose_output.json`，驱动场景中的标准 SMPL-X 骨架还原动作，并根据 `focal_length` 和 `cam_t` 自动创建一台对齐的 Camera，把原图设为相机的 Background Image（透明度 0.5）。”

### 阶段 3：打通 Rigify 与 VRM 二次元模型的一键重定向（第 4～5 天）
* **操作：** 将 `Rokoko/rokoko-studio-live-blender` 的 `retargeting.py` 和 `squall01337/mixamo-llm-mocap` 的 `retarget_smplx.py` 喂给 Agent。
* **给 Agent 的指令：**
  > “基于 Rest Pose 四元数偏移补偿算法，编写一个从内置 SMPL-X 中介骨架向 `Rigify` 和 `VRM` 标准骨骼重定向的模块。要求支持一键烘焙为关键帧，并提供三个后处理调整属性：`shoulder_relax`（降低锁骨耸肩角度）、`spine_influence`（脊柱弯曲权重）、`ground_snap`（自动计算脚底最低点并将根骨骼平移至 $Z=0$ 平面）。”

### 阶段 4：Blender 4.2+ Extension 面板封装与演示视频录制（第 6～7 天）
* **UI 设计（极简三步流）：**
  1. **Image Input：** 拖拽图片框 + 预览缩略图 + `[x] Auto Match Camera` 勾选项。
  2. **Target Rig：** 吸管工具吸取用户的角色骨架 + 预设下拉框（`Auto Detect` / `VRM & MMD` / `Rigify` / `Auto-Rig Pro` / `UE5 & Mixamo`）。
  3. **Generate & Tweak：** 醒目的 `Generate 3D Pose` 大按钮 + 下方三个实时微调滑块（肩膀放松、躯干夸张度、脚底贴地）。
* **引流与上架：** 准备 3 张高难度动作图（一张二次元插画、一张极限街舞/体操图、一张带复杂手势的写真），录屏展示“1 秒对齐原图透视 + 丝滑微调”的过程，同步发布至 B站、小红书、X，并在 Gumroad、Booth 与面包多上架。
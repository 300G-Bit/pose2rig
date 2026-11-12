# design_spec.md 复核报告与合并执行方案 v2

- 复核对象：`D:\blender5.2\pose_plugin\docs\design_spec.md`（351 行）
- 对照文档：`docs/blender_3d.md`、`docs/blender_3d_plugin_plan.md`
- 复核日期：2026-11-07
- 复核方法：源码固定 commit 阅读 + 本机 Blender 5.2.2 实测 + 许可证原文核对
- 结论：**设计说明书方向正确、结构可用，但存在 8 个 P0 阻断项；按原文直接开工会在相机、重定向、显存和许可四处返工。**

---

## 0. 结论摘要

1. **环境假设错误**：文档写“Blender 4.2+”，实际 `D:\blender5.2\blender.exe` 是 **Blender 5.2.2 LTS / Python 3.13.13**。manifest 写 4.2 可以构建，但代码与 wheel 必须按 5.2 的 Python ABI 单独验证。
2. **1.2 GB 峰值与 CameraHMR 不兼容**：CameraHMR 主干是 ViT-H/16（embed_dim=1280、depth=32，约 630M 参数），FP16 权重已约 1.26 GB；Detectron2 的 ViTDet-H 检测器再加约 1.26 GB。**仅权重就约 2.5 GB**，不可能压到 1.2 GB。
3. **商业许可链不成立**：CameraHMR 根许可证为空；SMPLer-X 是 S-Lab 非商业；SMPL-X 资产非商业；WiLoR 是 **CC BY-NC-ND 4.0**（非商业且禁止演绎）；YOLOv8 是 AGPL-3.0。按文档做 $29 付费版，法律风险高于技术风险。
4. **相机公式有竖图 bug**：`f_mm = f_px * 36 / W` 只在 W≥H 成立；竖图（二次元插画最常见）会算大约 33% 的焦距。通用式是 `f_px * 36 / max(W,H)`（AUTO sensor fit、方形像素）。
5. **“复用 smplx_blender_addon 的轴向修正”是误读**：该函数没有任何坐标轴修正，它只是把轴角转四元数直接写入**其专用骨架**；骨架 rest 轴向不匹配就会错。
6. **§6.3 的 `pose_bone.matrix` 写法会读到旧矩阵**：实测父骨旋转 90° 后，不调用 `view_layer.update()`，子骨 `matrix` 与更新后不同（DIFFERS=True）。应直接算 `matrix_basis`，不要依赖逐骨 `matrix` 赋值。
7. **§6.4 修改器作用在错误空间**：向 identity 做 Slerp 会连 rest pose 一起抹掉；贴地用了 `Bone.tail`（局部 rest 坐标，实测 (0,1,0)），不是 `PoseBone.tail`（姿态坐标）。
8. **契约缺关键字段**：`pose_result.json` 缺 `left_foot/right_foot`、根位移、rest 骨架、坐标系声明和每关节置信度，不能作为重定向的唯一真源。

---

## 1. 环境实测（先纠正版本）

| 项目 | 实测值 | 影响 |
|---|---|---|
| Blender | **5.2.2 LTS**，build hash `d13f752e3b9c`，2026-09-15 | 文档的“4.2+”只能作为最低声明，不能作为开发基线 |
| Python | **3.13.13** (MSC v.1944 64-bit) | 4.2 LTS 是 Python 3.11；wheel 需 cp311/cp313 两套 |
| `bpy.utils.extension_path_user` | 存在 | 用户数据目录方案可用 |
| `bpy.app.online_access` | 存在 | 下载器必须检查 |
| `Camera.background_images` | 存在 | 背景垫图方案可用 |
| `Camera.sensor_fit` | AUTO / HORIZONTAL / VERTICAL | 相机公式必须显式选 fit |
| `PoseBone.matrix` | 实例上存在 | 可用，但有更新时序陷阱（见 §4） |
| Extension 校验/构建 | 用 `blender_version_min="4.2.0"` 的 manifest 在 5.2.2 上 **validate + build 成功** | 说明 manifest 兼容，不等于代码兼容 |

补充：当前用户配置里安装了 Rokoko Studio Live、MMD Tools、Auto-Rig Pro、Ragdoll，并且 `polyhavenassets` 在启动时注册报错。**所有自动化测试必须用 `--factory-startup` 或独立测试配置**，否则日志被污染、结果不可复现。

建议支持矩阵：

- PoC：只承诺 **Blender 5.2.2 / Windows x64**。
- 4.2 LTS：等 PoC 通过后，用独立 CI 跑一遍再写进支持列表；不要现在写“4.2+”就默认兼容。
- 若打包原生 wheel：4.2 用 cp311，5.2 用 cp313，分别出 ZIP；`--split-platforms` 只分平台，不分 Python 版本。

---

## 2. 逐节评审

| 章节 | 内容 | 结论 | 说明 |
|---|---|---|---|
| 1.1–1.2 | 项目定位与指标 | **需修订** | 定位可保留；“≤1.2GB、0.4–0.8s、CPU≤2.5s、100% 释放”全部改为待实测目标 |
| 2 | 开源复用矩阵 | **需修订** | 仓库路径、分支、许可证多处不准确；见 §3 P0-3、§4 P1-5 |
| 3 | 三层架构 | **保留框架，需改实现** | 进程隔离正确；但“进程退出释放显存”与“0.4–0.8s”冲突；Copy Rotation 与 §6.3 公式二选一 |
| 4 | 目录结构 | **基本保留** | 增加 `schemas/`、`tests/`、`core/retarget_math.py`；`assets/bridge_smplx_rig.blend` 需许可审查 |
| 5.1 | `pose_result.json` | **需重写** | 字段不足、混用轴角/四元数、缺脚与 rest 数据；见 §6 |
| 5.2 | 骨骼映射预设 | **保留格式，需加校验** | 名字匹配有歧义；需角色+层级+左右侧校验与自定义映射 |
| 6.1 | 相机反推 | **需修正** | 竖图焦距 bug；SMPLer-X 的 `f_px` 经验公式是虚构的 |
| 6.2 | 罗德里格斯转四元数 | **需修正** | 不存在“轴向修正逻辑”；依赖 bridge rig 的 rest 轴向契约 |
| 6.3 | Rest Pose 偏移 | **公式方向正确，实现方式错误** | 不能逐骨赋值 `pose_bone.matrix` 而不更新；需转 armature space |
| 6.4 | 四个后处理 | **需重写** | 作用域、rest 基准、`Bone.tail` 三处错误 |
| 7.1 | UI 布局 | **保留** | 去掉 “(1s)” 字样；`Head Look at Cam`、`Save to Pose Lib` 需补设计 |
| 7.2 | Free/Pro 切分 | **需重做商业逻辑** | GPL 下代码对买家可见，功能门控可绕过；Free 版含 SMPL-X 骨架同样有许可问题 |
| 8 | 四阶段 Prompt | **保留骨架，验收标准要改** | 路径 `DESIGN_SPEC.md` 应为 `docs/design_spec.md`；“完全重合/零扭曲”不可度量 |

---

## 3. P0 阻断项（开工前必须解决）

### P0-1 1.2 GB 峰值与 CameraHMR 不兼容

**位置**：design_spec L11、L52–L54；blender_3d.md L4。

**证据**：

- CameraHMR `core/backbones/vit.py`：`embed_dim=1280, depth=32, num_heads=16`，即 ViT-H/16 规模，约 630M 参数；FP16 权重约 **1.26 GB**。
- CameraHMR `mesh_estimator.py` 同时初始化 `self.detector`（Detectron2 `cascade_mask_rcnn_vitdet_h_75ep`，ViTDet-H 主干约 630M 参数）和 `self.model`（CameraHMR ViT-H）。FP16 权重合计约 **2.5 GB+**，再加激活、输入和 CUDA context，6 GB 卡在 Blender 同时开视口时很容易 OOM。
- SMPLer-X 的参数量（README L71–L74）：S32 32M、B32 103M、L32 327M、H32 662M。FP16 分别约 64 MB、206 MB、654 MB、1.32 GB。**只有 S32/B32 有希望接近 1.2 GB 总峰值**。

**结论**：

- 若 1.2 GB 是硬指标，CameraHMR + Detectron2 ViTDet-H 直接出局。
- 必须做“引擎 × 检测器 × 精度”矩阵实测，不能先写指标再找模型。
- “100% 释放显存”改为“Worker 进程退出后由操作系统回收”；常驻 Worker 只能做到“显式卸载 + 尽力归还”，不能保证 100%。

**建议**：

- PoC 先测三条：CameraHMR + 轻量检测器（仅姿态质量基线）、SMPLer-X S32/B32（显存/速度基线）、SMPLer-X L32（质量上限）。
- 记录 `torch.cuda.max_memory_allocated` + `nvidia-smi` 整卡增量，四阶段采样（基线/加载/推理峰值/卸载后）。
- 指标未达标时改目标或换引擎，不能改测试口径。

### P0-2 商业许可链不成立

**位置**：design_spec L23–L29、L288–L299。

| 组件 | 实际许可 | 商业结论 |
|---|---|---|
| CameraHMR 代码 | GitHub API `license: null`；README 未声明 | 不能默认可商用；需作者书面授权 |
| CameraHMR 权重 | 官网注册下载，自带条款 | 需单独审查；不等于代码许可 |
| SMPLer-X 代码 | **S-Lab License 1.0，仅非商业** | 商业需联系 S-Lab |
| SMPL-X 模型/资产 | MPI 非商业许可 | 商业需 Meshcapade 商业许可 |
| WiLoR | **CC BY-NC-ND 4.0**（`license.txt` 原文确认） | 非商业 + **禁止演绎**；转 ONNX、改模型、打包都可能违约 |
| WiLoR-mini | 仓库无根许可证，是 WiLoR 的重打包 | 继承 WiLoR 限制，不能商用 |
| YOLOv8（若使用） | **AGPL-3.0** | 商业插件需 Ultralytics 企业许可，或换 Apache-2.0 检测器 |
| Detectron2 | Apache-2.0 | 可用 |
| PyTorch / timm | BSD / Apache-2.0 | 可用 |
| Rokoko Studio Live | **LGPL-3.0** | 可隔离使用；整段复制进 GPL 插件会改变义务，需复核 |
| Blender / Rigify | GPL | 插件本身按 GPL 分发；可收费，但源码义务 |

**结论**：

- 文档里“用户自己下载权重 = 合规”不成立。**End user 用非商业权重做商业工作也可能违约**；插件作者设计并引导该流程同样有风险。
- Pro 版“含 WiLoR 增强”在 CC BY-NC-ND 下基本不可行，除非单独取得授权。
- 若目标是 $29 付费产品，必须先做 **G0 许可门禁**：逐项拿到书面授权，或替换为许可明确的引擎/权重。
- 若只是研究 PoC，可以按研究条款使用，但不能上架、不能宣传为商业产品。

### P0-3 相机焦距竖图 bug

**位置**：design_spec L211–L215。

**问题**：

```
f_mm = f_px * S_w / W      # 仅当 W >= H 且 sensor_fit='AUTO'
```

竖图（H > W）时，AUTO fit 把 `sensor_width=36mm` 对应到**长边 H**，正确式是：

```
f_mm = f_px * sensor_width / max(W, H)      # AUTO + 方形像素
```

若显式设 `sensor_fit='HORIZONTAL'`，则 `f_mm = f_px * 36 / W`；若 `'VERTICAL'`，则 `f_mm = f_px * 36 / H`。**必须三选一并写进契约**，不能默认。

以 1200×1600 竖图为例：`f_px=2000`，正确 `f_mm=45mm`；按文档算 `60mm`，焦距偏大 33%，对应垂直 FOV 约 33.4°，而按 f_px 应有约 43.6°，视角明显更窄，人物会显得比背景大。

**另外**：

- design_spec L204 对 SMPLer-X 写 `f_px = sqrt(W² + H²)` 是**虚构经验公式**。SMPLer-X 实际使用配置虚拟焦距 5000（256×256 输入），再按 bbox 缩放：`focal = 5000 / 256 * bbox_width`。必须按引擎分别适配，不能统一套公式。
- `cam_rotation_euler=(π/2,0,0)` 假设人物直立、相机无 roll、根节点在世界原点。俯拍/仰拍/躺姿需要完整旋转矩阵，不能只用固定欧拉角。
- 主点 `cx,cy` 目前没有进入 Blender 相机；`fx≠fy` 时还要处理 pixel aspect。

**验收**：合成场景放已知 3D 点，用 `bpy_extras.object_utils.world_to_camera_view` 投影，横图/竖图/方图误差都应 < 1 px；真实图片只报告可验证的重投影误差。

### P0-4 “复用轴向修正逻辑”是误读

**位置**：design_spec L217–L223。

**事实**：

`smplx_blender_addon/__init__.py` 的 `set_pose_from_rodrigues` 只做：

```python
quat = Quaternion(axis, angle_rad)
armature.pose.bones[bone_name].rotation_quaternion = quat
```

**没有任何轴置换或坐标系修正**。它之所以正确，是因为该插件自带的 `smplx_model_300_20220615.blend` 骨架的 rest 局部轴与 SMPL-X 关节一一对应。换一个自行生成的 bridge rig，直接写四元数就会错。

**修正**：

- 若保留 bridge rig：必须在资产构建时导出每个关节的 rest 旋转矩阵，并验证 `bridge_rest == SMPL-X rest`（允许浮点误差）；否则不能直接写四元数。
- 更稳妥：统一用 `delta = R_pose @ R_rest.inverted()`，再作用到目标 rest，避免依赖“骨架刚好对齐”的隐含假设。
- 资产来源必须可追溯；`bridge_smplx_rig.blend` 即使无网格，关节层级与 rest 变换仍可能构成 SMPL-X 衍生数据，需许可审查。

### P0-5 §6.3 的 `pose_bone.matrix` 写法会读到旧矩阵

**位置**：design_spec L229–L237、L339。

**实测**（Blender 5.2.2，root→child 链，root 绕 Z 旋转 90°）：

```
CHILD_MATRIX_BEFORE_UPDATE = [[1,0,0,0],[0,0,-1,0],[0,1,0,1],[0,0,0,1]]
CHILD_MATRIX_AFTER_UPDATE  = [[0,-1,0,-1],[0,0,-1,0],[1,0,0,0],[0,0,0,1]]
DIFFERS = True
```

说明“按拓扑序单次遍历、避免 `view_layer.update()`”不成立。父骨改了之后，子骨的 `matrix` 在 depsgraph 更新前是旧值。

**另外**：`R_S,rest` 与 `R_T,rest` 若包含 Armature Object 变换，算出的 `R_T,target_world` 也在世界空间；直接赋给 `pose_bone.matrix`（armature space）会**重复应用对象变换**。必须左乘 `M_obj,T^{-1}`。

**修正（推荐）**：不写 `pose_bone.matrix`，直接算局部基：

```
# 全部在 armature space，3x3
P_b      = D_j @ B_rest_b          # 目标骨公共空间旋转
Basis_b  = (P_parent @ B_rel_b).inverted() @ P_b
pb.rotation_mode = 'QUATERNION'
pb.rotation_quaternion = Basis_b.to_quaternion()
```

这样不依赖 depsgraph 顺序，也不需要逐骨 update。若一定要用 `pose_bone.matrix`，则每层父骨之后必须 `view_layer.update()`，性能会差很多。

**Step C/D 的 Copy Rotation 与 §6.3 是两个方案，不能混用**：

- Copy Rotation 方案（Rokoko 风格）：在**源骨架**里复制一套与目标骨 rest 完全一致的新骨（head/tail/roll 取自目标），挂 `COPY_ROTATION`（必要时 `COPY_LOCATION`），再 Visual Keying 烘焙。缺了“复制目标 rest 骨”这一步，Copy Rotation 会把源骨的世界旋转直接覆盖到目标，rest 差全部变成错误。
- 直接矩阵方案：按上面公式算 `matrix_basis`，不建约束、不烘焙。
- 建议：**主路径用直接矩阵**；Copy Rotation + Visual Keying 只作为“兼容已有重定向工作流”的可选导出模式，并单独测试。

### P0-6 §6.4 修改器作用在错误空间

**位置**：design_spec L239–L252。

1. **Shoulder Relax**：`Slerp(q_collar, identity, 0.6α)` 会把锁骨的 **rest 朝向**也一起削掉。正确做法是对“相对 rest 的增量”做缩放：

```
q_delta = q_rest.inverted() @ q_pose
angle   = q_delta.angle * (1 - 0.6α)
q_new   = q_rest @ Quaternion(q_delta.axis, angle)
```

2. **Spine Curvature**：直接乘局部角同样包含 rest；应对 `q_delta` 的角度乘 β，再重组。
3. **Ground Snap**：文档用 `b.tail`，但 `Bone.tail` 是**局部 rest 坐标**。实测：`Bone.tail=(0,1,0)`，`Bone.tail_local=(0,0,2)`，`PoseBone.tail=(0,0,2)`。必须用 `PoseBone.tail`（姿态）或 evaluated mesh 的最低顶点；还要把结果从 armature space 转回对象空间再移根。
4. **Forearm Twist Split**：不能假设所有骨架的扭转轴都是 Y；需要按目标骨 roll/局部轴检测，且 50% 应做成参数。

### P0-7 数据契约不完整

**位置**：design_spec L111–L161。

问题清单：

- 缺 `left_foot` / `right_foot`（SMPL-X 55 关节里第 10、11 个），脚部朝向无法驱动。
- 缺根位移 `transl` 或明确“角色固定在原点、只移相机”的约定。
- 缺 rest 骨架（joint names、parents、rest positions、rest rotations），重定向无法验证。
- 缺坐标系/单位/手性声明；`global_orient` 是轴角，其他是四元数，混用易错。
- 缺每关节置信度；文档自己说“不伪造”，但 schema 没有 `null` 位置。
- `image_path` 用绝对路径，日志/分享会泄露用户目录；应改 `image_sha256` + 可选文件名。
- 没有 schema 版本迁移策略。

**修正**：采用 §6 的 CanonicalPose v1；原始模型输出只放 RawModelResult，不进 Blender。

### P0-8 “100% 零误差还原原图姿态”不可作为验收语

**位置**：design_spec L62、L323。

“驱动 bridge rig 100% 零误差”只能表示**复现预测参数**的数值误差为零，不能表示**与输入图片一致**。模型本身有预测误差，二次元域外误差更大。验收语应分开：

- 参数复现：矩阵/四元数往返误差 < 1e-6。
- 图像还原：重投影误差、人工评分、关键点误差，按数据集报告。

---

## 4. P1 高优先项

| # | 位置 | 问题 | 修正 |
|---|---|---|---|
| P1-1 | L52–L54 | YOLOv8n bbox 直接喂 CameraHMR 会错：CameraHMR 的 `box_size = expand_to_aspect_ratio(scale*200).max()`，不是裸 bbox 高 | 写专用 adapter，复现 `expand_to_aspect_ratio`；用同一 bbox 对比 CameraHMR 原管线 |
| P1-2 | L54 | Worker 每次退出 → 每次付 Python/CUDA/模型加载，0.4–0.8s 不可能 | 常驻 Worker 懒启动；冷/热分开报；空闲卸载是独立设置 |
| P1-3 | L12 | CPU 兜底 ≤2.5s：ViT-L/H + 双手在 CPU 上通常 10–30s | CPU 用 S32/B32；或删除该承诺，只保证“可运行” |
| P1-4 | L99 | `bridge_smplx_rig.blend` 无网格仍可能是 SMPL-X 衍生数据 | G0 审查；或改用许可清晰的合成骨架并记录来源 |
| P1-5 | L27 | Rokoko 路径 `core/bone_lists.py` 不存在；实际是 `core/auto_detect_lists/bones.py`；许可为 LGPL-3.0 | 修正引用；按 LGPL 做隔离与声明，不整段复制 |
| P1-6 | L168–L191 | 预设按名字匹配有歧义（`leftShoulder` 在 Mixamo 是锁骨，在别的骨架可能是上臂） | 角色 + 层级 + 左右侧 + 骨长比例校验；置信度低时要求用户确认；提供自定义映射 |
| P1-7 | L96、L350 | `ui/preferences.py` “一键安装 Python/ONNX 环境”是任意代码执行面 | 只允许签名 Runtime Pack；禁止任意 pip/脚本；哈希+签名+回滚 |
| P1-8 | L288–L299 | GPL 下 Free/Pro 同代码库，Pro 功能对买家可见、可绕过 | 商业价值放在权重/运行时/预设资产/服务；不要靠隐藏代码 |
| P1-9 | L323、L334 | “完全重合”“零扭曲”不可度量 | 改为：重投影 median/P90、关键点误差、rest 复现误差、人工评审表 |
| P1-10 | L311、L326、L337、L348 | Prompt 让 Agent 读 `DESIGN_SPEC.md`，实际文件是 `docs/design_spec.md` | 修正路径；或补一个根目录软链接/副本 |
| P1-11 | L40 | Windows 上 `detectron2`（git 安装）+ `chumpy` + `numpy==1.23.5` 很难装 | Worker 固定 Python 3.10 + 预编译 wheel/conda 环境；不要在 Blender 3.13 里装 |
| P1-12 | L53 | “SMPLer-X-Large (ViT-L) 6GB 性价比高”未实测 | 先测 S32/B32/L32 三档，按质量/显存/速度选，不先锁 L32 |

---

## 5. 修订后的数学规范

### 5.1 相机

输入约定：

- `f_px`：像素焦距，**必须注明是水平还是垂直**；方形像素下二者相等。
- `s`, `tx`, `ty`：模型在方形裁剪框上的弱透视参数。
- `b`：裁剪框边长（像素），按 CameraHMR 的 `box_size` 定义，即 `max(bbox_w, bbox_h)`（含 aspect 扩展）。
- `c_x, c_y`：裁剪框中心（原图像素）。

全图相机（相机坐标 X 右 / Y 下 / Z 前）：

```
T_Z = 2 * f_px / (s * b)
T_X = tx + 2 * (c_x - W/2) / (s * b)
T_Y = ty + 2 * (c_y - H/2) / (s * b)
```

Blender 相机（人物根节点在原点）：

```
P_cam = (-T_X, -T_Z, T_Y)
R_cam = Euler((pi/2, 0, 0))        # 仅适用于直立、无 roll
lens_mm = f_px * sensor_width / max(W, H)   # sensor_fit='AUTO'
```

如果 `sensor_fit='HORIZONTAL'`：`lens_mm = f_px * sensor_width / W`；`'VERTICAL'`：`/ H`。

SMPLer-X：

```
f_px = cfg.focal[0] / cfg.input_body_shape[1] * bbox_w
```

不是 `sqrt(W² + H²)`。

### 5.2 重定向

全部用 3×3 旋转，armature space：

```
D_j        = S_pose_j @ S_rest_j.inverted()          # 源关节世界增量
P_b        = D_j @ A_b @ B_rest_b                    # 目标公共空间旋转
Basis_b    = (P_parent @ B_rel_b).inverted() @ P_b   # 目标局部基
B_rel_b    = B_parent_rest.inverted() @ B_rest_b
```

- `A_b`：语义对齐；同构骨架为 identity；四肢可按 rest 方向对齐，足按 yaw 对齐，脊柱/颈/头一般不强制对齐。
- 未映射骨：继承父骨 rest-relative 旋转，不施加源骨扭转。
- 根位移：按腿长比例缩放，不直接写源 pelvis 米制坐标。
- 写入：`pb.rotation_mode='QUATERNION'; pb.rotation_quaternion = Basis_b.to_quaternion()`。
- 不修改用户 rest pose、不 `transform_apply` 用户骨架。

### 5.3 后处理

```
q_rest = pb.bone.matrix_local.to_quaternion()
q_pose = pb.rotation_quaternion
q_delta = q_rest.inverted() @ q_pose
q_new = q_rest @ Quaternion(q_delta.axis, q_delta.angle * factor)
```

- Shoulder Relax：`factor = 1 - 0.6α`，只作用于 collar 的 delta。
- Spine Curvature：`factor = β`，只作用于 spine1–3 的 delta。
- Ground Snap：`z_min = min(pb.tail.z for pb in foot_bones)`（armature space）或 evaluated mesh 最低点；根位移 = `-z_min` 转到对象空间。
- Forearm Twist：检测目标骨局部扭转轴；无 twist 骨时只对前臂 roll 做比例分配，默认 0.5 可调。

---

## 6. CanonicalPose 数据契约 v2（建议替换 pose_result.json）

```json
{
  "schema_version": "pose_result/v1",
  "request_id": "uuid",
  "engine": {
    "id": "camerahmr-smplx",
    "source_revision": "65d11a0640d23c60f55ec82ae54298e9e7e549e0",
    "runtime": "torch-fp16",
    "weights_sha256": "...",
    "license_record": "docs/licensing/camerahmr.md"
  },
  "image": {"width": 1200, "height": 1600, "sha256": "..."},
  "conventions": {
    "units": "m",
    "rotation": "row_major_3x3",
    "camera": "x_right_y_down_z_forward",
    "handedness": "right"
  },
  "source_skeleton": {
    "joint_names": ["pelvis", "left_hip", "...", "left_foot", "right_foot", "..."],
    "parents": [-1, 0, "..."],
    "rest_positions": ["..."],
    "rest_rotations": ["..."]
  },
  "local_pose_rotations": ["... per joint 3x3 ..."],
  "root_translation": [0.0, 0.0, 0.0],
  "camera": {
    "fx_px": 0.0, "fy_px": 0.0, "cx_px": 0.0, "cy_px": 0.0,
    "sensor_fit": "AUTO",
    "sensor_width_mm": 36.0,
    "model_to_camera": ["... 4x4 ..."]
  },
  "hands": {"enabled": true, "per_joint_confidence": ["..."]},
  "diagnostics": {"timings_ms": {}, "warnings": []}
}
```

原则：

- 原始模型输出 → RawModelResult；Blender 只读 CanonicalPose。
- 不伪造模型未提供的置信度；未知用 `null`。
- 旋转统一 3×3，避免轴角/四元数顺序混乱。
- 所有数组校验形状、有限值、正交性、行列式；拒绝 NaN/Inf。
- 不用 `pickle` / `allow_pickle=True` 加载下载内容。

---

## 7. 架构修订

保留 design_spec 的三层结构与目录，但改五点：

1. **Worker 常驻**：懒启动、单请求队列、空闲卸载；冷/热分别计时。不要每次进程退出。
2. **UI 回收用 `bpy.app.timers`**：后台线程只做 Popen/读管道/入队；`bpy.app.timers` 在主线程改场景。Modal Operator 可用于进度展示，但不作为唯一驱动。
3. **重定向主路径用 `matrix_basis` 直算**；Copy Rotation + Visual Keying 仅作可选导出模式。
4. **Bridge Rig 降级为可选调试视图**：不进入产品必需链路；若保留，必须锁定 rest 契约与资产许可。
5. **Runtime/Model Manager 分离**：Extension 只带 UI/数学/协议；Worker 运行时与模型权重独立签名、独立版本、独立回滚。

建议目录补充：

```text
pose2rig_blender/
  schemas/pose_result_v1.json
  schemas/model_catalog_v1.json
  core/retarget_math.py        # 纯 numpy/mathutils，可单测
  core/pose_modifiers.py
  worker/schema.py
  worker/engines/base.py
  worker/engines/camerahmr_torch.py
  worker/engines/smplerx_onnx.py
  tests/unit/
  tests/blender_headless/
  tests/golden/
  docs/licensing/
```

---

## 8. 许可 G0 门禁（商业发布前必须全部有结论）

| 组件 | 用途 | 当前状态 | 商业发布前动作 |
|---|---|---|---|
| CameraHMR 代码/权重 | 全身+相机基线 | 无根许可证 / 官网条款 | 取得书面授权，或替换 |
| SMPLer-X 代码/权重 | 备选全身 | S-Lab 非商业 | 取得商业授权，或替换 |
| SMPL-X 模型 | bridge rig / 蒙皮 | MPI 非商业 | 取得 Meshcapade 商业许可 |
| WiLoR / WiLoR-mini | 手部增强 | CC BY-NC-ND 4.0 | 不进入商业版；或单独授权 |
| YOLOv8 | 检测器候选 | AGPL-3.0 | 换 Apache-2.0 检测器，或企业许可 |
| Detectron2 / PyTorch / timm | 运行时 | Apache/BSD | 保留 notices |
| Rokoko | 重定向参考 | LGPL-3.0 | 隔离、动态链接、声明；法律复核 |
| Blender / Rigify | 宿主/预设 | GPL | 插件按 GPL 分发；源码义务 |
| Mixamo/MMD/ARP 角色 | 测试/预设 | 各自条款 | 不打包角色；只提供映射字典 |

结论：**G0 未通过前，不做付费版、不做“商业级”宣传、不发布含 SMPL-X/WiLoR 权重的安装包。** 可以先做研究 PoC。

---

## 9. 修订后的 7 天 PoC 计划

| 日期 | 交付 | 验收门槛 |
|---|---|---|
| D0（半天） | 环境基线：Blender 5.2.2、Worker Python 3.10、CameraHMR demo、GPU 驱动记录 | demo 可重复；记录 cold/warm、VRAM 四阶段；形成许可清单 |
| D1 | Worker CLI + RawModelResult + CanonicalPose v1 + schema 校验 | 同一图片输出确定；形状/有限值/正交性测试通过 |
| D2 | 相机适配器（CameraHMR + 可选 SMPLer-X） | 横/竖/方图合成投影 < 1px；真实图只报告可验证误差 |
| D3 | 纯数学重定向核心 + golden tests | identity、父链、rest offset、左右镜像、非均匀缩放全绿 |
| D4 | Mixamo + VRM 预设、FK、根缩放、预览/Undo | 标准 T/A-pose 角色无翻转、无父链扭曲 |
| D5 | 三个后处理 + 可选贴地 + 缺骨报告 | 滑块从不可变 base 重算，不累积；贴地不穿地 |
| D6 | 常驻 Worker + stdio IPC + timer 回收 + 极简面板 | 推理不卡 UI；取消/超时/崩溃不损坏场景 |
| D7 | 60 图报告 + 性能报告 + Go/No-Go | 明确达标/未达标；不包装成商业完成版 |

与 design_spec 四阶段的关系：D1–D2 = Stage 1；D3 = Stage 2；D4–D5 = Stage 3；D6 = Stage 4；D0/D7 是新增的基线与评审门。

---

## 10. 测试矩阵（最小可执行）

### 10.1 数学

- 轴角小角度、旋转矩阵↔四元数往返、NaN/Inf、正交性、行列式。
- identity 输入 → rest 精确复现（< 1e-6）。
- 单骨已知旋转、三级父链、左右镜像、A/T Pose、非均匀对象缩放。
- `matrix_basis` 写回后重算公共矩阵，与目标 < 1e-6。
- 未映射骨、重复映射、缺骨、循环映射、旧 request/generation 安全失败。

### 10.2 相机

- 已知焦距/主点/分辨率的合成场景，横/竖/方图。
- `sensor_fit` 三种模式分别测。
- `world_to_camera_view` 投影误差 < 1 px。
- 相机 roll/俯仰角不为零时的完整旋转矩阵测试。

### 10.3 重定向

- Mixamo YBot、VRM 示例、Rigify metarig 各一套 golden rig。
- 已知骨骼旋转 → 目标骨世界增量匹配。
- 手指 30 关节逐级验证；缺手指骨架时安全跳过。
- 脚底贴地：平底鞋/高跟/赤脚各一；不能只看骨 tail。

### 10.4 集成/性能

- 60 图：真人 30、二次元 30；遮挡/手势/广角/俯仰/蹲坐。
- UI 不卡；取消/超时/崩溃/无 GPU/GPU OOM。
- Windows 干净 VM；Blender 5.2.2；4.2 只在 CI 通过后声明。
- cold/warm P50/P95；VRAM 四阶段；FP16 vs FP32 的最终姿态误差。

---

## 11. 子智能体复核说明

之前启动的三个子任务：

1. **视觉模型仓库审计**：失败，未留消息。
2. **骨架/重定向仓库审计**：失败，未留消息。
3. **Extension/Worker/ONNX 打包调研**：成功，已回传完整报告并纳入本方案。

**是否需要重启 1、2？不需要。** 这两个任务的目标我已经在本轮直接完成，且证据更硬：

- CameraHMR：克隆并读取 `core/backbones/vit.py`、`core/camerahmr_model.py`、`core/heads/smplx_head_cliff_with_hands.py`、`mesh_estimator.py`、`core/datasets/dataset.py`、`requirements.txt`，固定 commit `65d11a0`。
- SMPLer-X：读取 `main/inference.py`、`README.md`、`LICENSE`，固定 commit `064baef`。
- WiLoR/WiLoR-mini：读取 `license.txt`（CC BY-NC-ND 4.0）、`wilor_mini/` 代码与 `setup.py`，固定 commit `ebec42f`。
- zjucxh / Meshcapade / Rokoko / mixamo-llm-mocap：读取 `__init__.py`、`operators/retargeting.py`、`core/auto_detect_lists/bones.py`、`pipeline/retarget_smplx.py` 与各 LICENSE，固定 commit 见附录。

**仍未被“读仓库”解决的**（重启子智能体也解决不了）：

- CameraHMR/SMPLer-X 在 RTX 3060 上的真实显存与耗时：必须跑实验。
- ONNX 导出可行性与 FP16 精度损失：必须写导出脚本和回归。
- CameraHMR 根许可证、WiLoR 商业授权：必须联系作者/律师。
- Blender 5.2 与 4.2 的真实兼容性：必须双版本 CI。

**建议**：如果要做独立复核，不要重启旧任务，直接开两个更小的任务：
- A. 只读审计本报告的 8 个 P0 数学/API 结论（半天）。
- B. 在 3060 上跑 CameraHMR/SMPLer-X 三档基准（需环境，1–2 天）。

---

## 12. 待确认决策

1. **目标**：研究 PoC，还是直接商业版？
   - 研究 PoC：按本报告 D0–D7 开工，可用 CameraHMR 研究条款。
   - 商业版：先做 G0，未拿到授权不进入模型集成。
2. **引擎**：CameraHMR（视角最好、最重、无根许可）vs SMPLer-X S32/B32（轻、非商业）vs 许可清晰的替代模型。
3. **硬指标优先级**：1.2 GB 与 0.8 s 在当前栈下不能同时成立；选一个作为硬门槛，另一个作为目标。
4. **Blender 范围**：PoC 只承诺 5.2.2；4.2 是否必须支持？若必须，预留双版本 CI 与 cp311 wheel。
5. **Bridge Rig**：保留（需许可资产+rest 契约）还是只做直接矩阵重定向（更轻、更可控）？

---

## 附录 A：源码证据（固定 commit）

- CameraHMR @ `65d11a0640d23c60f55ec82ae54298e9e7e549e0`
  - `core/backbones/vit.py` L12–L24：ViT-H/16（embed 1280、depth 32）
  - `core/camerahmr_model.py` L40–L55：输出旋转矩阵与双手
  - `mesh_estimator.py` L87–L132：Detectron2 ViTDet-H、`convert_to_full_img_cam`、垂直 FOV 焦距
  - `core/datasets/dataset.py` L56–L83：`box_size = expand_to_aspect_ratio(scale*200).max()`
  - `requirements.txt` L1–L18：detectron2 git、chumpy、numpy 1.23.5
- SMPLer-X @ `064baef0e4ab5277a3297691bc1d46ea5412586f`
  - `LICENSE` L1–L9：S-Lab 非商业
  - `README.md` L71–L74：S32/B32/L32/H32 参数量
  - `main/inference.py` L140–L178：SMPL-X 输出与虚拟焦距缩放
- WiLoR @ `license.txt` L1：CC BY-NC-ND 4.0
- WiLoR-mini @ `ebec42f94c389070cdd7dda6fd1bf0b4a659c960`
- zjucxh/smplx_blender_addon @ `310afb39d3b9ea84b10a8cbce40e20431acb1bab`
  - `__init__.py` L74–L107：`set_pose_from_rodrigues` 无轴修正
  - `LICENSE.md` L20–L57：GPL 代码 + SMPL-X 非商业
- Rokoko @ `b031e5a001b3d87e62359d18159c4e4ab479c732`
  - `LICENSE.md` L1–L17：LGPL-3.0
  - `operators/retargeting.py` L76–L219：复制目标 rest 骨 + Copy Rotation + bake
- mixamo-llm-mocap @ `da5e7cc48557f0272832429a8df3fbf2b3c1273d`
  - `pipeline/retarget_smplx.py` L20–L40、L1317–L1349：世界增量→局部基
  - `LICENSE` L1–L37：MIT + 第三方资产分离

## 附录 B：本机实测命令与结果

```text
D:\blender5.2\blender.exe --version
→ Blender 5.2.2 LTS, build hash d13f752e3b9c, 2026-09-15

blender --background --factory-startup --python-expr "..."
→ BLENDER_VERSION=5.2.2
→ PYTHON=3.13.13 (main, May 8 2026) [MSC v.1944 64 bit (AMD64)]
→ HAS_EXTENSION_PATH_USER=True
→ HAS_ONLINE_ACCESS=True
→ CAM_BG_IMAGES=True
→ CAM_SENSOR_FIT=['AUTO', 'HORIZONTAL', 'VERTICAL']

pose_bone.matrix 时序测试（root 绕 Z 90°，child 不 update）：
→ CHILD_MATRIX_BEFORE_UPDATE 与 AFTER_UPDATE 不同，DIFFERS=True

Bone.tail vs PoseBone.tail：
→ Bone.tail=(0,1,0)（局部 rest）
→ Bone.tail_local=(0,0,2)（armature rest）
→ PoseBone.tail=(0,0,2)（姿态）

extension validate/build（blender_version_min="4.2.0"）：
→ Success parsing TOML
→ building pose2rig_test-1.0.0.zip；complete
```

---

## 附录 C：建议直接采用的默认值

- 开发基线：Blender **5.2.2**，Windows x64。
- Worker：独立 **Python 3.10**（CameraHMR/SMPLer-X 依赖），Blender 内不装 Torch。
- 相机：`sensor_fit='AUTO'`，`lens_mm = f_px * 36 / max(W,H)`。
- 重定向：直接 `matrix_basis`；不修改用户 rest pose。
- 后处理：全部基于 `q_delta = q_rest^-1 q_pose`。
- 契约：`schema_version = "pose_result/v1"`，旋转统一 3×3 行主序。
- 测试：所有 Blender 自动化用 `--factory-startup`。
- 发布：G0 未过 → 只做研究 PoC，不做付费版。

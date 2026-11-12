# Blender 单图转 3D 骨骼姿态插件制作方案（技术核验版）

- 日期：2026-11-07
- 状态：待用户确认；本阶段不编写实现代码
- 输入文档：`C:\Users\22502\Downloads\blender_3d.md`
- 首发建议：Windows x64，优先适配实际安装的 Blender；支持版本必须以 `blender --version` / `bpy.app.version` 实测，不能只凭目录名 `D:\blender5.2` 判断
- **状态更新（2026-11-07）**：本文件为初版调研方案。`design_spec.md` 加入后，已由 [design_spec_review.md](design_spec_review.md) 逐节复核并修订；执行以复核报告的 v2 方案为准。

## 0. 执行结论

建议把原文的“7 天完成商业插件”拆成两个目标：

1. **7 天研究型 PoC**：验证单图推理、统一数据契约、相机投影、Mixamo 与 VRM 基本重定向、非阻塞 Blender UI。
2. **额外 2～4 周产品化**：扩充测试集与骨架预设、完善异常恢复和 Model Manager、做安装/升级/回滚、评估 ONNX/FP16，并完成许可证门禁。

核心路线：

- **先 PyTorch 原始管线，后 ONNX**。先证明输出值得优化，避免同时调试模型导出、坐标系、GPU 环境和插件 UI。
- **薄 Extension + 常驻独立 Worker + 长度分帧 stdio IPC**。Blender 进程不加载 Torch/ORT/CUDA，Worker 不导入 `bpy`。
- **统一 CanonicalPose 数据契约**。前端不直接依赖 CameraHMR、SMPLer-X 或 WiLoR 的原始输出。
- **直接数学重定向为主，调试 Proxy Rig 可选**。隐藏 SMPL-X 骨架不是产品链路的必需中间件。
- **首发 Mixamo + VRM，Rigify 随后**。VRM 是二次元目标，Mixamo 用作标准骨架基准；MMD、UE5、Auto-Rig Pro 不进入第一版承诺。
- **0.8 秒、1.2 GB、精准还原均作为待实测目标，不作为销售承诺**。
- **商业发布设置独立许可证门禁**。用户自行下载权重不等于自动获得商业使用权；独立进程也不是许可证规避手段。

## 1. 对原文的关键修正

| 原表述 | 源码核验结果 | 对方案的影响 |
|---|---|---|
| CameraHMR 的 `bedlam2` 分支支持 SMPL-X | 当前远程只有 `master`；SMPL-X/BEDLAM2 文档与代码在主分支。网络输出是旋转矩阵，双手各 15 个关节 | 固定 commit 做技术基线，不寻找不存在的分支；适配器不要一律按轴角解析 |
| 复用 `demo.py` 即可得到 `pose_result.json` | 当前 demo 保存 OBJ 与叠加图，没有保存完整姿态 JSON；需要自己定义输出契约 | 第一阶段必须有独立 Adapter 与 schema 测试 |
| CameraHMR 使用 YOLOv8n-pose，约 10 ms | 当前实现使用 Detectron2 检测器 | 原文耗时和显存没有依据；检测器替换必须做质量回归 |
| `zjucxh/smplx_blender_addon` 提供通用 `C_axis` / `rodrigues_to_quat` | 实际核心函数是 `set_pose_from_rodrigues`，直接把轴角四元数写到其专用骨架，没有通用 `C_axis` | 只能参考其专用骨架约定，不能照搬到任意 Rigify/VRM/Mixamo |
| Rokoko 是 GPL，文件为 `retargeting.py`、`bone_lists.py`、`operators/retarget.py` | 当前仓库是 LGPL-3.0；实现位于 `core/retargeting.py`、`core/auto_detect_lists/bones.py`、`operators/retargeting.py` | 可研究自动映射与约束烘焙，但不整段复制其产品流程；许可证义务按实际复用方式审查 |
| `f_mm = f_px * 36 / max(W,H)` 可通用对齐 | 该式在 `sensor_fit='AUTO'`、方形像素且 `f_px` 为像素焦距时成立；`sensor_fit` 为 HORIZONTAL/VERTICAL 或像素非方形时需改式；主点与相机坐标系仍需单独处理 | 契约中显式写 `sensor_fit`；以 `view_frame` / `world_to_camera_view` 回归测试；竖图不能套 `f_px*36/W` 的简化式 |
| SMPLer-X 可直接替代 CameraHMR 做真实焦距估计 | SMPLer-X 的推理代码使用配置中的虚拟焦距并按 bbox 缩放 | 它可比较姿态质量，但不等价于 CameraHMR 的图像焦距估计 |
| WiLoR-mini 是即插即用的商业手部外挂 | 当前代码是 PyTorch FP16，不是现成 ONNX；本仓库未声明根许可证，且还涉及原 WiLoR/MANO/权重条款 | 列为可选技术尖峰，不进 MVP 主链路 |
| 模型由用户下载即可商业合规 | SMPLer-X 代码明确限制非商业用途；SMPL-X 资产另有许可；CameraHMR 根许可证未声明 | 商业版必须获得相应授权或替换为许可明确的引擎；下载器只解决分发体积与安装，不创造权利 |

## 2. MVP 范围

### 2.1 第一版包含

- 单人、单张 PNG/JPEG/WebP；优先完整身体可见。
- 真人照片与二次元插画分别报告质量，不把动漫图与真实训练域混为一个准确率。
- 身体 21 个 SMPL-X 姿态关节、根旋转/根位移、双手各 15 关节；低置信手部可关闭。
- 透视相机、原图背景、焦距/画面偏移/角色缩放/地面高度的手动修正。
- Mixamo 与 VRM humanoid 预设、必填骨缺失报告、用户映射保存。
- 三个非破坏调整：`shoulder_relax`、`spine_influence`、`ground_snap`。
- Generate 异步预览、Apply 一次性应用、完整 Undo；可选插入单帧关键帧。
- CPU 正确性回退；GPU 不可用时明确提示性能差异。
- 研究 PoC 使用手动配置 Worker 环境；产品版再启用签名 Runtime/Model Manager。

### 2.2 第一版不包含

- 视频、多人、跨帧跟踪、面部表情、眼球和口型。
- 任意遮挡/极端动漫变形都“精准还原”的保证。
- 自动恢复真实身高、真实镜头参数或像素级重合保证。
- Rigify/Auto-Rig Pro 的控制器语义全自动适配；MMD、UE5 预设。
- TensorRT 必选依赖、WiLoR 默认二次推理。
- 在未取得授权时把研究模型包装成可商用产品。

## 3. 总体架构

```text
Blender Extension（主线程执行全部 bpy 操作）
  ├─ Panel / Preferences / Operators
  ├─ Job Supervisor：单请求队列、状态机、取消、超时、代次
  ├─ Worker Client：长度分帧 stdio、schema 校验、心跳与结构化错误
  ├─ Pose Store：不可变 CanonicalPose + 可重复计算的调整参数
  ├─ Retarget Engine：CanonicalPose → RigProfile → 目标局部姿态
  ├─ Camera / Ground / Preview / Undo
  └─ Runtime Manager + Model Manager（相互独立）
                 │ 子进程 stdio；图片传规范化路径
                 ▼
Independent Worker（固定私有 CPython，禁止 import bpy）
  ├─ Hello / capabilities 协商
  ├─ 输入校验与图像预处理
  ├─ Engine Adapter
  │    ├─ CameraHMR PyTorch（研究基线）
  │    ├─ ONNX Runtime CUDA/CPU（后续可替换后端）
  │    └─ Hand Refiner（可选，默认关闭）
  ├─ CanonicalPose Builder + 数值校验
  └─ 分阶段计时、显存采样、日志与取消
```

### 3.1 进程与 UI 规则

- 点击 Generate 只快照输入并入队，不在 UI 线程调用阻塞式 `communicate()`。
- 后台线程负责进程与 IPC；结果进入有界 `queue.Queue`；`bpy.app.timers` 在 Blender 主线程回收并修改场景。
- 第一版只允许一个活跃推理请求。消息带 `protocol_version`、`request_id`、`worker_generation` 和 deadline；旧代次结果直接丢弃。
- Worker 懒启动并预热；预热是独立、可取消阶段。常驻是为了避免每次支付 Python/CUDA/模型加载成本。
- 提供“空闲自动卸载”选项，但 UI 要提示下次冷启动成本。独立进程不会消除与 Blender 的 GPU 显存竞争。
- 取消先在阶段边界协作执行；超时后终止并重启进程树。崩溃只自动重启一次，保留退出码和有界 stderr 日志。
- 结果完整校验后一次性预览/应用，禁止半结果修改用户骨架。

### 3.2 关键架构取舍

| 决策 | 优点 | 代价 | 结论 |
|---|---|---|---|
| PyTorch 先行，ONNX 后置 | 快速建立质量与数值基线，问题可定位 | 研究环境较大 | 采用；ONNX 以相同 CanonicalPose 做回归 |
| stdio 而非 localhost HTTP | 无端口、防火墙和 socket 认证复杂度，生命周期清晰 | 通常只服务一个父进程 | 采用；多客户端需求出现时再评估 Named Pipe/socket |
| CanonicalPose 而非前端直接吃模型字典 | 模型可替换、schema 可测试、许可与版本可追踪 | 需要编写适配器 | 采用 |
| 直接重定向而非必须隐藏 Proxy Rig | 少一层骨架和场景状态，易于纯数学测试 | 必须提供可靠源骨架 rest 数据 | 采用；Proxy Rig 仅作调试视图 |
| 常驻 Worker 而非每图退出 | 热路径才可能接近低延迟 | 常驻显存与崩溃恢复复杂 | 采用，并配空闲卸载 |

## 4. 数据契约

分两层：

1. **RawModelResult**：引擎原始输出，仅供适配器和诊断，不进入 Blender UI。
2. **CanonicalPose**：跨引擎稳定格式，Blender 只消费此格式。旋转统一为行主序 3×3 矩阵，避免轴角/6D/四元数顺序混乱。

建议 `pose_result/v1` 至少包含：

```json
{
  "schema_version": "pose_result/v1",
  "request_id": "uuid",
  "engine": {
    "id": "camerahmr-smplx",
    "source_revision": "immutable-commit",
    "runtime": "torch-fp16",
    "weights_sha256": "...",
    "license_record": "..."
  },
  "image": {"width": 1920, "height": 1080, "sha256": "..."},
  "person": {"bbox_xyxy": [0, 0, 0, 0], "detector_confidence": 0.0},
  "conventions": {
    "units": "m",
    "rotation": "row_major_3x3",
    "camera": "x_right_y_down_z_forward"
  },
  "source_skeleton": {
    "joint_names": ["pelvis", "left_hip", "..."],
    "parents": [-1, 0, "..."],
    "rest_positions": ["... per-joint xyz ..."],
    "rest_rotations": ["... per-joint 3x3 ..."]
  },
  "local_pose_rotations": ["... per-joint 3x3 ..."],
  "model_to_camera": ["... row-major 4x4 ..."],
  "camera": {"fx_px": 0.0, "fy_px": 0.0, "cx_px": 0.0, "cy_px": 0.0},
  "optional_hands": {"enabled": true, "confidence": null},
  "diagnostics": {"timings_ms": {}, "warnings": []}
}
```

约束：

- 不伪造模型没有提供的逐关节置信度；未知值用 `null`。
- `source_skeleton` 可由 Worker 从当次模型/rest 数据生成，前端不捆绑 MPI 网格资产；其派生数据许可仍需审查。
- `model_to_camera` 明确模型坐标到相机坐标，禁止只传含义模糊的 `cam_t`。
- 调试时可落盘 JSON；生产热路径直接通过 IPC 传同一 schema。
- 不使用 `pickle` / `allow_pickle=True` 加载下载结果；所有数组做形状、有限值、正交性和行列式校验。

## 5. 重定向与相机数学规范

### 5.1 重定向

对源关节 `j` 与映射目标骨 `b`：

1. 在源骨架公共空间求姿态旋转增量：
   `D_j = S_pose_j · inverse(S_rest_j)`。
2. 目标公共空间旋转：
   `P_b = D_j · A_b · B_rest_b`。
   - `B_rest_b`：目标骨 rest 旋转。
   - `A_b`：语义骨方向/rest pose 对齐；完全同构时为 identity。
   - 四肢、足、脊柱可分别使用不同对齐策略，不能所有骨共用一个固定轴置换。
3. 未映射目标骨继承父骨的 rest-relative 旋转，不随意施加源骨扭转。
4. 转回目标局部姿态（旋转形式）：
   `Basis_b = inverse(P_parent · B_rel_b) · P_b`。
   Blender 落地时使用完整 4×4、`bone.matrix_local`、父链与 armature space；对象 `matrix_world` 单独处理。
5. 根位移按角色比例单独缩放，不把源 pelvis 的米制坐标原样写到任意目标。
6. 不对用户原骨架执行“应用全部变换”或修改 rest pose。预览用副本/独立数据，应用时只写约定的 pose 通道。

`zjucxh` 中“轴角直接赋给 pose bone”只在其专用 SMPL-X 骨架约定下成立，不能代替上述父链与 rest 对齐。

### 5.2 比例与贴地

- FK 重定向与足部 IK 分层；先得到稳定身体姿态，再做可选下肢修正。
- 根缩放可先用腿部长度比，角色高度只作辅助；记录被修改的根通道。
- 单图没有视频接触序列，`ground_snap` 只能基于当前姿态的鞋底/脚部几何与地面平面，不使用虚构的接触检测。
- 贴地必须选择“只移根”或“根 + 腿部 IK”，并限制膝踝异常拉伸；低置信时只给手动地面高度。

### 5.3 相机

- 明确源相机约定。OpenCV 常见 `x right / y down / z forward` 到 Blender 相机 `x right / y up / z backward` 需要完整变换，不能只重排三个平移分量。
- 像素焦距换算必须配合显式 `sensor_fit`。在 `sensor_fit='AUTO'` 且方形像素时用 `f_mm = f_px * 36 / max(W,H)`；`HORIZONTAL` 用 `/W`，`VERTICAL` 用 `/H`。竖图不能套 `f_px*36/W`。
- 主点通过相机 shift/投影约定处理；`fx != fy` 时检查 pixel aspect，不假装总是方形像素。
- 以 `Camera.view_frame(scene=...)` 和 `bpy_extras.object_utils.world_to_camera_view` 做横图、竖图、方形图和已知 3D→2D 点的回归。
- 相机焦距与目标角色放置分开：源模型的 `cam_t` 不能不经比例变换直接套到 VRM/Mixamo。
- 产品文案使用“估计并对齐视角”，只有明确测试集上的重投影误差才能量化效果，不能承诺普遍“像素级重合”。

## 6. 建议仓库结构

```text
repo/
  blender_extension/
    blender_manifest.toml
    __init__.py
    preferences.py
    ui/panel.py
    application/job_supervisor.py
    application/pose_store.py
    ipc/client.py
    rig/canonical.py
    rig/retarget.py
    rig/profiles/mixamo.json
    rig/profiles/vrm.json
    camera/projection.py
    scene/preview.py
    delivery/runtime_manager.py
    delivery/model_manager.py
  worker/
    pyproject.toml
    src/pose_worker/server.py
    src/pose_worker/schema.py
    src/pose_worker/engines/base.py
    src/pose_worker/engines/camerahmr_torch.py
    src/pose_worker/engines/camerahmr_onnx.py
    src/pose_worker/benchmark.py
  schemas/pose_result_v1.json
  schemas/model_catalog_v1.json
  tests/unit/
  tests/worker_integration/
  tests/blender_headless/
  tests/golden/
  docs/adr/
  docs/licensing/
  tools/export_onnx.py
  tools/benchmark.py
```

Blender Extension ZIP 只放前端及真正由 Blender 导入的依赖。Torch、ORT、私有 CPython、CUDA/cuDNN/TensorRT 不属于 Blender wheels，放入独立、按平台版本化的 Runtime Pack。

## 7. Model / Runtime Manager 与许可证门禁

### 7.1 分成两个管理器

- **Runtime Manager**：安装可执行 Worker、私有 Python 和原生依赖；独立签名、版本兼容和回滚。
- **Model Manager**：只安装数据权重与显式 external data；模型 catalog 不允许声明 pip 包、启动命令或任意代码。

### 7.2 信任链

- catalog 固定上游 commit/release，记录 URL、文件大小、SHA-256、权重 provenance、输出 schema、runtime 兼容范围、许可证全文/digest。
- 发行商对 canonical catalog 签名，前端钉住公钥；SHA-256 只校验完整性，不能单独证明发布者身份。
- 下载前展示准确版本和许可证，记录用户确认；确认不授予额外权利。未知/非商用/禁止转换或再分发的条目在商业策略下默认阻止。
- HTTPS、系统证书、host allowlist、重定向复核、大小限制、有界重试、临时文件、流式哈希、同卷原子 rename、并发锁和旧版本回滚。
- 默认使用 `bpy.utils.extension_path_user`，不写扩展安装目录、Blender 安装目录或全局 Python。
- 防止路径穿越、zip-slip、symlink/junction、external-data 越界；离线路径也重新校验 digest 和根目录。
- 遵守 `bpy.app.online_access` 与 Extension 的 `network` / `files` 权限声明；离线模式零网络。
- 保存 SBOM、第三方 notices、转换工具链和模型来源。商业热路径不直接下载并反序列化不可信 `.pt/.ckpt/pickle`。

### 7.3 商业发布 G0 门禁

逐项登记：代码、检测器、 backbone、模型权重、SMPL-X/MANO 资产、纹理、测试图片、示例角色、ONNX 转换产物和 NVIDIA 运行库。

只有以下两条之一通过才进入商业发布：

1. 获得覆盖实际使用、转换、分发方式的商业授权并留档；或
2. 替换为许可证与商业目标兼容的引擎/资产，并完成新的质量回归。

“代码 GPL/LGPL 是否允许收费”“进程边界是否影响许可”“生成姿态是否属于受限衍生数据”等按真实复用和分发方式做法律复核，不用技术架构代替法律结论。

## 8. 测试与验收指标

### 8.1 数学与数据（必须先全绿）

- 轴角小角度、旋转矩阵/四元数往返、NaN/Inf、正交性、行列式。
- identity 输入得到精确 rest；单骨已知旋转、父子链、左右镜像、A/T Pose、非均匀对象缩放。
- 局部姿态写回后重新求公共空间矩阵，与目标矩阵误差在约定浮点容差内。
- 未映射骨、重复映射、缺骨、循环映射、错误 schema、旧 request/generation 均安全失败。
- 横图/竖图/方形图、不同主点、已知焦距的合成相机投影；应用与 Undo 后场景快照一致。
- 调整滑块每次从不可变 base pose 重算，不随拖动累积误差。

### 8.2 Worker / Blender 集成

- 无人、多人、低置信、损坏图片、非 ASCII/长路径、GPU OOM、无 GPU。
- 预热/推理中取消、各阶段超时、Worker 崩溃、stderr 洪峰、损坏/超大响应、Blender 退出无孤儿进程。
- UI 保持可交互；全部 `bpy` 场景变更只在主线程；连续运行无句柄和内存泄漏。
- 每个目标 Blender 版本做 headless 测试和干净 Windows VM 安装测试；未经实测的版本不写入支持矩阵。

### 8.3 质量数据集

PoC 至少 60 张、调参集与验收集分离：真人 30、二次元 30，覆盖站姿、街舞/体操、蹲坐、遮挡、手势、广角、俯仰拍、横竖图。测试图片与角色也必须可合法使用。

指标：

- 检测/有效输出成功率，按真人与动漫分别统计。
- 有人工关键点或可靠标注时的归一化重投影误差 median/P90；无标注结果只作视觉评审，不伪造准确率。
- 固定评审表记录肢体错误、左右颠倒、扭曲、手部可用性、地面与视角主观评分。
- 相机在合成已知参数场景中的投影误差；真实图片只报告可验证指标。
- 阈值在 P1 基线后冻结，不能看完结果再修改口径。

### 8.4 性能口径

- 固定确切 GPU SKU、驱动、功耗模式、Blender 场景、模型 digest、输入尺寸与 runtime。
- cold 与 warm 分开，batch=1，报告 P50/P95 与失败率。
- 端到端从点击到场景应用及 depsgraph 更新，包含解码、检测、推理、IPC 和 Blender 操作。
- 记录检测/身体/手部/后处理/Blender 各阶段，手部开关分别测。
- 显存记录同场景基线、session 加载、推理峰值、卸载后；同时记录 Worker PID 与整卡增量及噪声。
- FP32 与 FP16/混合精度比较最终 CanonicalPose、重定向和投影误差，不只比较网络张量。
- 未达到 0.8 秒或 1.2 GB 时发布真实结果或调整目标，不修改测试口径制造达标。

## 9. 7 天 PoC 执行计划

| 天数 | 交付 | 验收门槛 |
|---|---|---|
| D1 | 固定 CameraHMR commit 与原始 PyTorch 环境；记录实际 Blender/Python/GPU；建立许可清单和测试集 | 原始 demo 可重复运行；不是先转 ONNX |
| D2 | `infer_single_image` 适配器、RawModelResult、CanonicalPose v1、结构化诊断 | 同一图片输出确定；形状/数值/schema 测试通过；有 cold/warm 基线 |
| D3 | 纯数学源骨架、重定向核心、合成骨架 golden tests、相机投影测试 | identity/父链/rest/横竖图全绿后才进入 UI |
| D4 | Mixamo profile、基本 FK、根缩放、预览与 Undo | 标准 T/A-pose 测试角色无左右颠倒和父链扭曲 |
| D5 | VRM profile、缺骨报告、三个非破坏调整、可选贴地 | 两种目标复用同一 CanonicalPose；滑块不累积 |
| D6 | 常驻 Worker、stdio IPC、timer 回收、Generate/Preview/Apply 极简面板 | 推理不卡 UI；取消/超时/崩溃不损坏场景 |
| D7 | 60 图 PoC 报告、性能报告、限制清单、演示与 Go/No-Go 评审 | 明确哪些指标达标、哪些失败；不包装成商业完成版 |

PoC 明确排除：ONNX 全量迁移、WiLoR、自动 Model Manager、全部骨架预设、商业上架。

## 10. PoC 后产品化顺序

1. **质量优先（3～5 天）**：扩充验收集，修复系统性姿态/相机/比例问题，冻结 VRM 与 Mixamo 预设。
2. **工程硬化（3～5 天）**：Runtime/Model Manager、签名与哈希、离线导入、安装/升级/回滚、干净 VM 测试。
3. **ONNX 技术尖峰（3～5 天，可中止）**：先导出检测器之外的单个核心网络，再逐步处理预处理和其他子网；比较输出与最终姿态。失败则保留 PyTorch Worker，不阻塞插件主线。
4. **性能优化（按数据安排）**：CUDA FP32 正确性 → FP16/混合精度 → 固定形状和常驻热路径 → 再判断 TensorRT 是否值得额外依赖。
5. **手部增强（仅指标驱动）**：先证明现有双手输出不足，再评估 WiLoR 的 MANO→SMPL-X/目标骨坐标对齐和许可成本。
6. **第二批骨架**：Rigify deform/control 分离，再评估 MMD、UE5、Auto-Rig Pro；每类独立 golden rig 与映射预设。
7. **发布门禁**：质量、性能、崩溃恢复、许可、SBOM、安装更新和文档全部通过后，才制作销售文案与演示。

## 11. 主要风险与停止条件

| 风险 | 等级 | 缓解 / 停止条件 |
|---|---|---|
| 商业授权不成立 | 高 | G0 未过则只做研究 PoC，不上架；更换引擎或取得书面授权 |
| 动漫图域外泛化差 | 高 | 单列动漫验收集；若基本肢体可用性不足，缩小支持范围而非宣称精准 |
| 重定向矩阵错误 | 高 | 数学 golden tests 未全绿，停止 UI/预设扩张 |
| 相机对齐公式不稳定 | 高 | 合成投影测试先通过；提供手动焦距/偏移，不作像素级保证 |
| ONNX 导出或 FP16 精度损失 | 中高 | 后端可替换；以 CanonicalPose 回归，失败保留 PyTorch |
| 6 GB 显存或热延迟不达标 | 中高 | 分阶段 profiling；减少常驻模型/输入规格须重新测质量，不能隐瞒回退 |
| VRM/Mixamo 实际变体过多 | 中 | 缺骨报告 + 自定义映射；不无限承诺 Auto Detect |
| 下载供应链与升级损坏 | 中高 | 签名 catalog、哈希、原子安装、回滚、离线模式和干净 VM 测试 |

## 12. 待确认的四个产品决策

推荐默认值：

1. **先做什么**：先做研究型 PoC，不同时承诺商业上架。
2. **Blender 范围**：优先实际安装版本，随后验证 4.2/4.5 LTS；支持列表以测试为准。
3. **骨架顺序**：Mixamo + VRM 先行，Rigify 第二批。
4. **性能策略**：常驻 Worker + 可配置空闲卸载；cold/warm 分开公布，0.8 秒仅作目标。

若同意，建议确认语：**“按推荐方案做 7 天研究型 PoC，先 D1/D2，不做 ONNX。”**

若目标是直接商业发布，则先确认：**“先做 G0 许可证与可商用模型替代评估。”** 在 G0 通过前，不进入商业模型集成。

## 13. 主要证据（固定源码版本）

### CameraHMR @ 65d11a0640d23c60f55ec82ae54298e9e7e549e0

- [SMPL-X/BEDLAM2 demo 与下载要求](https://github.com/pixelite1201/CameraHMR/blob/65d11a0640d23c60f55ec82ae54298e9e7e549e0/docs/bedlam2.md#L24-L38)
- [网络输出 reshape 为旋转矩阵并包含双手](https://github.com/pixelite1201/CameraHMR/blob/65d11a0640d23c60f55ec82ae54298e9e7e549e0/core/camerahmr_model.py#L40-L55)
- [SMPL-X head 的身体与左右手参数](https://github.com/pixelite1201/CameraHMR/blob/65d11a0640d23c60f55ec82ae54298e9e7e549e0/core/heads/smplx_head_cliff_with_hands.py#L92-L106)
- [Detectron2 检测器与 full-image camera 转换](https://github.com/pixelite1201/CameraHMR/blob/65d11a0640d23c60f55ec82ae54298e9e7e549e0/mesh_estimator.py#L87-L118)
- [由垂直 FOV 计算像素焦距](https://github.com/pixelite1201/CameraHMR/blob/65d11a0640d23c60f55ec82ae54298e9e7e549e0/mesh_estimator.py#L120-L132)
- [demo 当前只导出网格和叠加图](https://github.com/pixelite1201/CameraHMR/blob/65d11a0640d23c60f55ec82ae54298e9e7e549e0/mesh_estimator.py#L140-L191)

### SMPLer-X @ 064baef0e4ab5277a3297691bc1d46ea5412586f

- [S-Lab License：非商业使用与商业联系条款](https://github.com/caizhongang/SMPLer-X/blob/064baef0e4ab5277a3297691bc1d46ea5412586f/LICENSE#L1-L9)
- [推理输出 SMPL-X 参数与虚拟焦距/主点处理](https://github.com/caizhongang/SMPLer-X/blob/064baef0e4ab5277a3297691bc1d46ea5412586f/main/inference.py#L140-L178)

### SMPL-X Blender Add-on @ 310afb39d3b9ea84b10a8cbce40e20431acb1bab

- [轴角直接写入其专用 pose bone](https://github.com/zjucxh/smplx_blender_addon/blob/310afb39d3b9ea84b10a8cbce40e20431acb1bab/__init__.py#L74-L107)
- [GPL 代码、SMPL-X 模型与非商业条款说明](https://github.com/zjucxh/smplx_blender_addon/blob/310afb39d3b9ea84b10a8cbce40e20431acb1bab/LICENSE.md#L20-L57)

### Rokoko Studio Live @ b031e5a001b3d87e62359d18159c4e4ab479c732

- [当前许可证为 LGPL-3.0](https://github.com/Rokoko/rokoko-studio-live-blender/blob/b031e5a001b3d87e62359d18159c4e4ab479c732/LICENSE.md#L1-L17)
- [自动映射、rest 处理、约束与烘焙流程](https://github.com/Rokoko/rokoko-studio-live-blender/blob/b031e5a001b3d87e62359d18159c4e4ab479c732/operators/retargeting.py#L76-L219)

### mixamo-llm-mocap @ da5e7cc48557f0272832429a8df3fbf2b3c1273d

- [源增量、rest 对齐与坐标空间的明确说明](https://github.com/squall01337/mixamo-llm-mocap/blob/da5e7cc48557f0272832429a8df3fbf2b3c1273d/pipeline/retarget_smplx.py#L20-L40)
- [公共旋转到局部姿态及写回后复核](https://github.com/squall01337/mixamo-llm-mocap/blob/da5e7cc48557f0272832429a8df3fbf2b3c1273d/pipeline/retarget_smplx.py#L1317-L1349)
- [MIT 与第三方资产许可分离说明](https://github.com/squall01337/mixamo-llm-mocap/blob/da5e7cc48557f0272832429a8df3fbf2b3c1273d/LICENSE#L1-L37)

### 官方 API / 打包 / 运行时

- [Blender Extension manifest 与构建](https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html)
- [Blender Extension Python wheels](https://docs.blender.org/manual/en/latest/advanced/extensions/python_wheels.html)
- [Blender Camera.sensor_fit](https://docs.blender.org/api/current/bpy.types.Camera.html#bpy.types.Camera.sensor_fit)
- [Blender world_to_camera_view](https://docs.blender.org/api/current/bpy_extras.object_utils.html#bpy_extras.object_utils.world_to_camera_view)
- [Blender timers](https://docs.blender.org/api/4.2/bpy.app.timers.html) 与 [线程限制](https://docs.blender.org/api/4.2/info_gotcha.html)
- [ONNX Runtime CUDA EP 与依赖矩阵](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)
- [ONNX Runtime FP16/混合精度及精度风险](https://onnxruntime.ai/docs/performance/model-optimizations/float16.html)

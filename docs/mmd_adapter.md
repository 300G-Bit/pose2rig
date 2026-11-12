# MMD（PMX）骨架适配说明

## 测试模型

- `D:/Models/爱莉希雅女仆_by_神帝宇_.../爱莉希雅女仆.pmx`
- MMD Tools 导入后：`爱莉希雅女仆_arm`，499 骨；网格高约 **1.71 m**（标准比例，不是大头小人）
- 导入命令：`bpy.ops.mmd_tools.import_model(filepath=..., scale=0.08, types={'MESH','ARMATURE'}, clean_model=True)`

## 预设

新增 `assets/presets/mmd.json`，检测条件：骨架中存在 `センター` / `上半身` / `左腕` / `右腕`。

| SMPL-X 源关节 | MMD 目标骨（候选） |
|---|---|
| pelvis | `センター` / `下半身` |
| spine1 | `上半身` |
| spine2 | `上半身2` |
| neck | `首` |
| head | `頭` |
| left/right_collar | `肩.L` / `肩.R` |
| left/right_shoulder | `腕.L` / `腕.R` |
| left/right_elbow | `ひじ.L` / `ひじ.R` |
| left/right_wrist | `手首.L` / `手首.R` |
| left/right_hip | `足.L` / `足.R` |
| left/right_knee | `ひざ.L` / `ひざ.R` |
| left/right_ankle | `足首.L` / `足首.R` |
| left/right_foot | `つま先.L` / `つま先.R` |
| 30 根手指 | `親指０/１/２`、`人指１/２/３`、`中指...`、`薬指...`、`小指...`，带 `.L/.R` 后缀 |

注意：MMD Tools 可能把日文左右骨名导出为 `腕.L` / `腕.R` 等后缀形式，且手指数字是**全角** `１/２/３`；预设同时包含两种写法。

## 验证结果

- `build_mapping`：**51 骨**（21 身体 + 30 手指）
- 应用 mock 姿态后网格高 1.707 m，说明 rest/父链没有被破坏
- 应用真实 S32 姿态后网格可变形；具体视觉质量仍需在正面机位下评审
- 测试渲染：`docs/mmd_pose_test.png`（仅作链路证明，默认机位未优化）

## 使用

1. Blender 5.2.2 用 MMD Tools 导入 PMX。
2. Pose2Rig 面板选择目标骨架（`*_arm`），Preset 选 **MMD**。
3. 生成/滑杆/Apply 即可；若缺骨，检查是否使用了非标准 PMX 骨架。

MMD 模型本身有作者的使用条款，不能随插件分发；测试时只使用本地文件。

# 审查证据目录

本目录是 `docs/feature_audit_20261111.md` 的配套证据。

| 文件 | 说明 |
|---|---|
| `mmd_rest.png` | MMD 真实模型（爱莉希雅女仆，499 骨）rest 姿态正面渲染，高度 1.705 m |
| `mmd_mock.png` | 同一模型应用 Mock fixture 后的正面渲染；高度仍 1.705 m，说明 Mock 小旋转无法暴露坐标问题 |
| `mmd_real_s32.png` | 同一模型应用真实 S32 姿态后的正面渲染；角色翻倒/蜷缩，bbox Z 上界 0.641 m、总高 0.935 m |
| `person_left.jpg` | 真实 S32 测试输入；画面中存在多名人物，不是单人裁剪 |
| `person_left_halfbody.jpg` | 上述图片裁成上半身（330×402），半身图测试输入 |
| `original_mmd_pose_test.png` | 仓库原有 MMD 测试渲染，供对照 |
| `fix_compare.png` | 输入图 / MMD rest / 当前 S32 / 修正坐标系后的 S32 四联对照，见 `docs/audit_issue_analysis.md` |
| `real_s32_last_pose.json` | 真实 S32 全图推理的完整 pose_result/v1 |
| `halfbody_s32_pose.json` | 半身裁切图推理的完整 pose_result/v1 |
| `verification_summary.json` | 本次复跑的关键数值摘要（机器可读） |

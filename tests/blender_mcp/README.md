# Blender MCP 测试清单（Pose2Rig 5.2.2）

前置条件：

1. Blender **5.2.2** 正在运行，官方 MCP 扩展 Auto Start 已开启，监听 **127.0.0.1:9896**。
2. `bl_ext.user_default.pose2rig` 已安装并启用。
3. 参考图存在：`_research/repos/CameraHMR/demo_images/pexels-bertellifotografia-3856033.jpg`。

## 步骤

1. 检查通道：
   ```powershell
   python tools/mcp_official_client.py --code "import bpy; print('.'.join(map(str,bpy.app.version)))"
   ```
2. 运行插件 smoke：
   ```powershell
   python tools/mcp_official_client.py --file tests/blender_mcp/mcp_smoke.py
   ```
3. 预期 stdout：`blender=[5,2,2], addon=true, panel=true, scene_prop=true`，随后状态从 `Running...` 变为 `Done: N bones`。
4. 查询：
   ```powershell
   python tools/mcp_official_client.py --code "import bpy,json; s=bpy.context.scene.pose2rig; print(json.dumps({'status':s.status,'has_pose':bool(s.last_pose_json),'camera':bool(bpy.context.scene.camera)}, ensure_ascii=False))"
   ```

## 已知注意

- DSH 的 `blender_rt_*` 工具走 Goo Engine 4.4 / 9876，不要用它测试 5.2 插件。
- 5.2.2 官方 MCP 使用 **9896**；`tools/mcp_official_client.py` 是该协议的轻量客户端。
- 如果 9896 不通，先检查 Blender 5.2 是否运行、MCP 扩展 Auto Start 是否启用。

import bpy

for name in ("Cube", "Camera", "Light"):
    obj = bpy.data.objects.get(name)
    if obj:
        bpy.data.objects.remove(obj, do_unlink=True)
arm = bpy.data.objects.get("TargetRig")
if arm:
    arm.show_in_front = True
    arm.data.display_type = "STICK"
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
area = next((a for a in bpy.context.screen.areas if a.type == "VIEW_3D"), None)
if area:
    r3 = area.spaces[0].region_3d
    r3.view_location = (0.0, 0.0, 0.9)
    r3.view_distance = 2.8
    r3.view_perspective = "PERSP"
    area.spaces[0].show_region_ui = True
bpy.context.view_layer.update()
_ = bpy.ops.screen.screenshot(filepath=r"D:\blender5.2\pose_plugin\docs\pose2rig_real_s32.png")
result = {"ok": True, "objects": [o.name for o in bpy.data.objects]}

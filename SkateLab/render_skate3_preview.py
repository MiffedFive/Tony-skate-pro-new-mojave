"""Render one diagnostic frame per action from a generated Skate 3 blend.

Run inside Blender with ``--background file.blend --python this_file -- out``.
The script writes only disposable PNG previews outside the mod package.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


args = sys.argv[sys.argv.index("--") + 1 :]
output = Path(args[0]).resolve()
output.mkdir(parents=True, exist_ok=True)

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = 640
scene.render.resolution_y = 640
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = True
scene.display.shading.cavity_type = "WORLD"
scene.world.color = (0.045, 0.045, 0.055)

camera_data = bpy.data.cameras.new("MojaveSkatePreviewCamera")
camera = bpy.data.objects.new(camera_data.name, camera_data)
bpy.context.collection.objects.link(camera)
scene.camera = camera
camera.data.type = "ORTHO"
camera.data.ortho_scale = 2.35
camera.location = (3.2, -4.8, 2.35)
look_at(camera, Vector((0.0, 0.0, 0.9)))

armature = bpy.data.objects["Skate3_RX2_Rig"]
if armature.animation_data is None:
    armature.animation_data_create()
for track in armature.animation_data.nla_tracks:
    track.mute = True

for index, action in enumerate(sorted(bpy.data.actions, key=lambda item: item.name)):
    armature.animation_data.action = action
    start, end = (int(round(value)) for value in action.frame_range)
    frame = start + (end - start) // 2
    scene.frame_set(frame)
    safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in action.name)
    scene.render.filepath = str(output / f"{index:02d}_{safe_name}_f{frame:03d}.png")
    bpy.ops.render.render(write_still=True)
    print(f"RENDERED {action.name} frame={frame} path={scene.render.filepath}")

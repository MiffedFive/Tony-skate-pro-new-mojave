"""Render diagnostic stick figures from retarget_skate3_to_fnv.py output."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


DISPLAY_PARENTS = {
    "Bip01 Spine": "Bip01 Pelvis",
    "Bip01 Spine1": "Bip01 Spine",
    "Bip01 Spine2": "Bip01 Spine1",
    "Bip01 Neck": "Bip01 Spine2",
    "Bip01 Neck1": "Bip01 Neck",
    "Bip01 Head": "Bip01 Neck1",
    "Bip01 L Clavicle": "Bip01 Neck",
    "Bip01 L UpperArm": "Bip01 L Clavicle",
    "Bip01 L Forearm": "Bip01 L UpperArm",
    "Bip01 L Hand": "Bip01 L Forearm",
    "Bip01 R Clavicle": "Bip01 Neck",
    "Bip01 R UpperArm": "Bip01 R Clavicle",
    "Bip01 R Forearm": "Bip01 R UpperArm",
    "Bip01 R Hand": "Bip01 R Forearm",
    "Bip01 L Thigh": "Bip01 Pelvis",
    "Bip01 L Calf": "Bip01 L Thigh",
    "Bip01 L Foot": "Bip01 L Calf",
    "Bip01 L Toe0": "Bip01 L Foot",
    "Bip01 R Thigh": "Bip01 Pelvis",
    "Bip01 R Calf": "Bip01 R Thigh",
    "Bip01 R Foot": "Bip01 R Calf",
    "Bip01 R Toe0": "Bip01 R Foot",
}


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_segment(start: Vector, end: Vector, color: tuple[float, float, float, float]) -> None:
    delta = end - start
    if delta.length < 0.001:
        return
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=10,
        radius=1.25,
        depth=delta.length,
        location=(start + end) * 0.5,
    )
    obj = bpy.context.object
    obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    obj.color = color


args = sys.argv[sys.argv.index("--") + 1 :]
source_path = Path(args[0]).resolve(strict=True)
output = Path(args[1]).resolve()
output.mkdir(parents=True, exist_ok=True)
data = json.loads(source_path.read_text(encoding="utf-8"))

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = 640
scene.render.resolution_y = 640
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "OBJECT"
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = True
scene.world.color = (0.035, 0.035, 0.045)

camera_data = bpy.data.cameras.new("FNVRetargetCamera")
camera = bpy.data.objects.new(camera_data.name, camera_data)
bpy.context.collection.objects.link(camera)
scene.camera = camera
camera.data.type = "ORTHO"
camera.data.ortho_scale = 135.0
camera.location = (125.0, 220.0, 120.0)
look_at(camera, Vector((0.0, 0.0, 58.0)))

for index, (action_name, action) in enumerate(sorted(data["actions"].items())):
    for obj in list(bpy.data.objects):
        if obj is not camera:
            bpy.data.objects.remove(obj, do_unlink=True)

    frame_index = len(action["frames"]) // 2
    frame = action["frames"][frame_index]
    positions = {
        name: Vector(tuple(payload["world_matrix"][offset] for offset in (3, 7, 11)))
        for name, payload in frame.items()
    }
    for name, point in positions.items():
        if " L " in name:
            color = (0.95, 0.25, 0.2, 1.0)
        elif " R " in name:
            color = (0.2, 0.45, 1.0, 1.0)
        else:
            color = (0.85, 0.85, 0.9, 1.0)
        parent = DISPLAY_PARENTS.get(name)
        if parent in positions:
            add_segment(positions[parent], point, color)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.8, location=point)
        bpy.context.object.color = color

    safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in action_name)
    scene.render.filepath = str(output / f"{index:02d}_{safe_name}_f{frame_index + 1:03d}.png")
    bpy.ops.render.render(write_still=True)
    print(f"RENDERED {action_name} frame={frame_index + 1} path={scene.render.filepath}")

"""Export decoded Skate 3 armature-space matrices from Blender to JSON.

Run inside Blender with::

    blender --background source.blend --python export_skate3_actions.py -- \
        clips.json output.json
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import bpy


HUMAN_BONES = (
    "HIPS",
    "SPINE",
    "SPINE1",
    "SPINE2",
    "SPINE3",
    "NECK",
    "NECK1",
    "HEAD",
    "LEFTSHOULDER",
    "LEFTARM",
    "LEFTFOREARM",
    "LEFTHAND",
    "RIGHTSHOULDER",
    "RIGHTARM",
    "RIGHTFOREARM",
    "RIGHTHAND",
    "LEFTUPLEG",
    "LEFTLEG",
    "LEFTFOOT",
    "LEFTTOEBASE",
    "RIGHTUPLEG",
    "RIGHTLEG",
    "RIGHTFOOT",
    "RIGHTTOEBASE",
)


def flatten(matrix) -> list[float]:
    return [float(matrix[row][column]) for row in range(4) for column in range(4)]


args = sys.argv[sys.argv.index("--") + 1 :]
catalog_path = Path(args[0]).resolve(strict=True)
output_path = Path(args[1]).resolve()
catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
metadata = {item["name"]: item for item in catalog["clips"]}

armature = bpy.data.objects["Skate3_RX2_Rig"]
if armature.animation_data is None:
    armature.animation_data_create()
for track in armature.animation_data.nla_tracks:
    track.mute = True

result = {
    "schema": 1,
    "armature": armature.name,
    "bones": {
        name: {
            "parent": armature.data.bones[name].parent.name
            if armature.data.bones[name].parent
            else None,
            "rest_matrix": flatten(armature.data.bones[name].matrix_local),
        }
        for name in HUMAN_BONES
    },
    "actions": {},
}

for action in sorted(bpy.data.actions, key=lambda item: item.name):
    if action.name not in metadata:
        continue
    armature.animation_data.action = action
    start, end = (int(round(value)) for value in action.frame_range)
    frames = []
    for frame in range(start, end + 1):
        bpy.context.scene.frame_set(frame)
        frames.append(
            {
                name: flatten(armature.pose.bones[name].matrix)
                for name in HUMAN_BONES
            }
        )
    clip = metadata[action.name]
    result["actions"][action.name] = {
        "fps": float(clip["fps"]),
        "source_frames": int(clip["frames"]),
        "frame_start": start,
        "frame_end": end,
        "frames": frames,
    }
    print(f"EXPORTED {action.name} frames={len(frames)} fps={clip['fps']}")

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
print(f"WROTE {output_path} actions={len(result['actions'])}")

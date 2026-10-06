#!/usr/bin/env python3
"""Retarget decoded Skate 3 action matrices onto the Fallout NV biped.

The output is derived transform metadata, not a distributable Skate 3 asset.
It is used as an intermediate for KF generation and offline pose validation.
"""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
import sys
import time

import numpy as np


SOURCE_TO_TARGET = {
    "HIPS": "Bip01 Pelvis",
    "SPINE": "Bip01 Spine",
    "SPINE1": "Bip01 Spine1",
    "SPINE2": "Bip01 Spine2",
    "NECK": "Bip01 Neck",
    "NECK1": "Bip01 Neck1",
    "HEAD": "Bip01 Head",
    "LEFTSHOULDER": "Bip01 L Clavicle",
    "LEFTARM": "Bip01 L UpperArm",
    "LEFTFOREARM": "Bip01 L Forearm",
    "LEFTHAND": "Bip01 L Hand",
    "RIGHTSHOULDER": "Bip01 R Clavicle",
    "RIGHTARM": "Bip01 R UpperArm",
    "RIGHTFOREARM": "Bip01 R Forearm",
    "RIGHTHAND": "Bip01 R Hand",
    "LEFTUPLEG": "Bip01 L Thigh",
    "LEFTLEG": "Bip01 L Calf",
    "LEFTFOOT": "Bip01 L Foot",
    "LEFTTOEBASE": "Bip01 L Toe0",
    "RIGHTUPLEG": "Bip01 R Thigh",
    "RIGHTLEG": "Bip01 R Calf",
    "RIGHTFOOT": "Bip01 R Foot",
    "RIGHTTOEBASE": "Bip01 R Toe0",
}


def matrix(values: list[float]) -> np.ndarray:
    return np.asarray(values, dtype=np.float64).reshape(4, 4)


def orthogonalize(value: np.ndarray) -> np.ndarray:
    u, _singular, vt = np.linalg.svd(value)
    result = u @ vt
    if np.linalg.det(result) < 0:
        u[:, -1] *= -1.0
        result = u @ vt
    return result


def local_matrix(node) -> np.ndarray:
    row_rotation = np.array(
        [
            [node.rotation.m_11, node.rotation.m_12, node.rotation.m_13],
            [node.rotation.m_21, node.rotation.m_22, node.rotation.m_23],
            [node.rotation.m_31, node.rotation.m_32, node.rotation.m_33],
        ],
        dtype=np.float64,
    )
    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = row_rotation.T * float(node.scale)
    result[:3, 3] = (node.translation.x, node.translation.y, node.translation.z)
    return result


def flatten(value: np.ndarray) -> list[float]:
    return [float(item) for item in value.reshape(-1)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actions", type=Path, required=True)
    parser.add_argument("--skeleton", type=Path, required=True)
    parser.add_argument("--pyffi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.pyffi.resolve(strict=True)))
    time.clock = time.perf_counter
    inspect.getargspec = inspect.getfullargspec
    from pyffi.formats.nif import NifFormat as N

    source = json.loads(args.actions.resolve(strict=True).read_text(encoding="utf-8"))
    nif = N.Data()
    with args.skeleton.resolve(strict=True).open("rb") as stream:
        nif.read(stream)

    nodes = {}
    parents = {}
    order = []

    def walk(node, parent_name: str | None, parent_world: np.ndarray) -> None:
        raw_name = getattr(node, "name", b"")
        name = raw_name.decode(errors="replace") if isinstance(raw_name, bytes) else str(raw_name)
        world = parent_world @ local_matrix(node)
        if name:
            nodes[name] = {"node": node, "local": local_matrix(node), "world": world}
            parents[name] = parent_name
            order.append(name)
            parent_name = name
        for child in getattr(node, "children", ()):
            if child is not None and hasattr(child, "children"):
                walk(child, parent_name, world)

    walk(nif.roots[0], None, np.eye(4, dtype=np.float64))
    missing = sorted(set(SOURCE_TO_TARGET.values()) - set(nodes))
    if missing:
        raise KeyError(f"target skeleton is missing mapped bones: {missing}")

    source_rest = {
        name: matrix(payload["rest_matrix"])
        for name, payload in source["bones"].items()
    }
    axis = np.diag((-1.0, -1.0, 1.0))
    source_feet = (source_rest["LEFTFOOT"][:3, 3] + source_rest["RIGHTFOOT"][:3, 3]) * 0.5
    target_feet = (
        nodes["Bip01 L Foot"]["world"][:3, 3]
        + nodes["Bip01 R Foot"]["world"][:3, 3]
    ) * 0.5
    source_span = np.linalg.norm(source_rest["HEAD"][:3, 3] - source_feet)
    target_span = np.linalg.norm(nodes["Bip01 Head"]["world"][:3, 3] - target_feet)
    translation_scale = float(target_span / source_span)

    target_to_source = {target: source_name for source_name, target in SOURCE_TO_TARGET.items()}
    actions = {}
    for action_name, action in source["actions"].items():
        output_frames = []
        for source_frame in action["frames"]:
            pose_world = {}
            frame_bones = {}
            for target_name in order:
                rest_local = nodes[target_name]["local"]
                parent_name = parents[target_name]
                parent_pose = pose_world.get(parent_name, np.eye(4, dtype=np.float64))
                source_name = target_to_source.get(target_name)
                if source_name is None:
                    local_pose = rest_local
                else:
                    source_pose = matrix(source_frame[source_name])
                    source_rest_rotation = orthogonalize(source_rest[source_name][:3, :3])
                    source_pose_rotation = orthogonalize(source_pose[:3, :3])
                    source_world_delta = source_pose_rotation @ source_rest_rotation.T
                    target_world_delta = axis @ source_world_delta @ axis.T
                    desired_world_rotation = (
                        target_world_delta
                        @ orthogonalize(nodes[target_name]["world"][:3, :3])
                    )
                    parent_rotation = orthogonalize(parent_pose[:3, :3])
                    local_pose = rest_local.copy()
                    local_pose[:3, :3] = parent_rotation.T @ desired_world_rotation
                    if target_name == "Bip01 Pelvis":
                        source_delta = source_pose[:3, 3] - source_rest[source_name][:3, 3]
                        # Horizontal donor root travel must not be applied to the
                        # visual pelvis. FNV locomotion and Mojave Skate physics
                        # already move the actor through Bip01/root controllers.
                        # Keeping it here would move the body twice and snap it
                        # back whenever a push clip loops. Retain only authored
                        # vertical compression/bob from the Skate 3 pose.
                        source_delta[0] = 0.0
                        source_delta[1] = 0.0
                        desired_world_position = (
                            nodes[target_name]["world"][:3, 3]
                            + axis @ source_delta * translation_scale
                        )
                        local_pose[:3, 3] = parent_rotation.T @ (
                            desired_world_position - parent_pose[:3, 3]
                        )
                pose_world[target_name] = parent_pose @ local_pose
                if source_name is not None:
                    row_rotation = orthogonalize(local_pose[:3, :3]).T
                    rotation = N.Matrix33()
                    (
                        rotation.m_11,
                        rotation.m_12,
                        rotation.m_13,
                        rotation.m_21,
                        rotation.m_22,
                        rotation.m_23,
                        rotation.m_31,
                        rotation.m_32,
                        rotation.m_33,
                    ) = row_rotation.reshape(-1)
                    quat = rotation.get_scale_quat()[1]
                    frame_bones[target_name] = {
                        "translation": [float(value) for value in local_pose[:3, 3]],
                        "rotation": [float(quat.w), float(quat.x), float(quat.y), float(quat.z)],
                        "world_matrix": flatten(pose_world[target_name]),
                    }
            output_frames.append(frame_bones)
        actions[action_name] = {
            "fps": float(action["fps"]),
            "frames": output_frames,
        }
        print(f"RETARGETED {action_name} frames={len(output_frames)} fps={action['fps']}")

    result = {
        "schema": 1,
        "translation_scale": translation_scale,
        "axis_conversion": "rotate-180-degrees-around-z",
        "mapping": SOURCE_TO_TARGET,
        "target_rest": {
            name: {
                "parent": parents[name],
                "local_matrix": flatten(nodes[name]["local"]),
                "world_matrix": flatten(nodes[name]["world"]),
            }
            for name in SOURCE_TO_TARGET.values()
        },
        "actions": actions,
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    print(f"WROTE {output} scale={translation_scale:.6f} actions={len(actions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

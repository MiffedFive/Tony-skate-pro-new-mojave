#!/usr/bin/env python3
"""Build private test KF files from the Skate 3 -> FNV retarget metadata.

The generated KFs contain only transformed animation data for local testing.
They deliberately keep the already proven FNV/Sigma Bip01 root controllers so
the native player controller and Mojave Skate physics remain unchanged.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "vendor" / "python"))
time.clock = time.perf_counter
inspect.getargspec = inspect.getfullargspec
from pyffi.formats.nif import NifFormat as N


GROUPS = {
    "mtidle": ("Idle", ("R_STAND_IDLE2_N_0_CYC",), False),
    # CYC1 and CYC2 are complementary halves. Each half snaps by ~38 degrees
    # when looped alone, while the two cross-boundaries differ by only ~1.4.
    "mtforward": ("Forward", ("R_PUSHLSP_LSTR_N_0_CYC1", "R_PUSHLSP_LSTR_N_0_CYC2"), True),
    "mtfastforward": ("FastForward", ("R_PUSHLSP_LSTR_N_0_CYC1", "R_PUSHLSP_LSTR_N_0_CYC2"), True),
    "mtbackward": ("Backward", ("R_STAND_IDLE2_N_0_CYC",), True),
    "mtfastbackward": ("FastBackward", ("R_STAND_IDLE2_N_0_CYC",), True),
    "mtleft": ("Left", ("GR_GROUND_FS_CARVE_L_CYC",), True),
    "mtfastleft": ("FastLeft", ("GR_GROUND_FS_CARVE_L_CYC",), True),
    "mtright": ("Right", ("GR_GROUND_FS_CARVE_R_CYC",), True),
    "mtfastright": ("FastRight", ("GR_GROUND_FS_CARVE_R_CYC",), True),
    "mtturnleft": ("TurnLeft", ("GR_GROUND_FS_CARVE_L_CYC",), False),
    "mtturnright": ("TurnRight", ("GR_GROUND_FS_CARVE_R_CYC",), False),
}

# Conditional kNVSE overrides use the same locomotion group IDs and the same
# proven FNV root controllers as the centre set.  Only the retargeted body pose
# changes, so selecting a carve cannot turn Forward into a strafe/turn group
# and therefore cannot cancel HoldControl's native forward movement.
CARVE_GROUPS = {
    "carve_left": {
        "mtidle": ("Idle", ("GR_GROUND_FS_CARVE_L_CYC",), False),
        "mtforward": ("Forward", ("GR_GROUND_FS_CARVE_L_CYC",), True),
        "mtfastforward": ("FastForward", ("GR_GROUND_FS_CARVE_L_CYC",), True),
    },
    "carve_right": {
        "mtidle": ("Idle", ("GR_GROUND_FS_CARVE_R_CYC",), False),
        "mtforward": ("Forward", ("GR_GROUND_FS_CARVE_R_CYC",), True),
        "mtfastforward": ("FastForward", ("GR_GROUND_FS_CARVE_R_CYC",), True),
    },
}


def text(value) -> str:
    return value.decode(errors="replace") if isinstance(value, bytes) else str(value)


def read_nif(path: Path):
    data = N.Data()
    with path.open("rb") as stream:
        data.read(stream)
    return data


def normalize_quaternion(values):
    length = math.sqrt(sum(float(item) ** 2 for item in values))
    if length < 1.0e-8:
        raise ValueError("zero-length quaternion")
    return tuple(float(item) / length for item in values)


def assemble_cycle(actions, names):
    selected = [actions[name] for name in names]
    fps = float(selected[0]["fps"])
    if any(abs(float(action["fps"]) - fps) > 1.0e-6 for action in selected):
        raise ValueError(f"cycle parts have mismatched frame rates: {names}")
    frames = []
    for action in selected:
        frames.extend(action["frames"])
    # An explicit copy of frame zero at the end makes Gamebryo's wrap exact.
    frames.append(frames[0])
    return {"fps": fps, "frames": frames}


def set_quaternion(target, values) -> None:
    target.w, target.x, target.y, target.z = values


def make_transform_block(name, node, frames, duration):
    rotations = [normalize_quaternion(frame[name]["rotation"]) for frame in frames]
    # q and -q describe the same rotation. Keeping adjacent keys in one
    # hemisphere prevents the linear Gamebryo interpolator taking a long arc.
    for index in range(1, len(rotations)):
        if sum(a * b for a, b in zip(rotations[index - 1], rotations[index])) < 0.0:
            rotations[index] = tuple(-item for item in rotations[index])

    interp = N.NiTransformInterpolator()
    translation = frames[0][name]["translation"]
    interp.translation.x, interp.translation.y, interp.translation.z = translation
    set_quaternion(interp.rotation, rotations[0])
    interp.scale = float(node.scale)

    data = N.NiTransformData()
    data.num_rotation_keys = len(rotations)
    data.rotation_type = 1  # linear quaternion keys, as used by shipped FNV KFs
    data.quaternion_keys.update_size()
    denom = max(1, len(rotations) - 1)
    for index, (key, rotation) in enumerate(zip(data.quaternion_keys, rotations)):
        key.time = duration * index / denom
        set_quaternion(key.value, rotation)

    if name == "Bip01 Pelvis":
        data.translations.num_keys = len(frames)
        data.translations.interpolation = 1
        data.translations.keys.update_size()
        for index, (key, frame) in enumerate(zip(data.translations.keys, frames)):
            key.time = duration * index / denom
            value = frame[name]["translation"]
            key.value.x, key.value.y, key.value.z = value

    interp.data = data
    controlled = N.ControllerLink()
    controlled.interpolator = interp
    controlled.priority = 20
    controlled.node_name = name.encode()
    controlled.controller_type = b"NiTransformController"
    return controlled


def stationary_nonaccum(reference_sequence):
    """Freeze the proven runtime anchor without accumulated movement.

    PlayGroupAlt replaces the stock Idle, including its NonAccum controller.
    Omitting that anchor leaves the body/attached board in the wrong space.
    Skeleton.nif splits its bind height into Bip01; runtime KF puts that height
    and a 90-degree basis into NonAccum. Copying the bind NonAccum (identity!)
    buries the actor. Sample the proven Forward anchor, not the bind skeleton.
    The constant transform does not add any physical/root displacement.
    """
    source = next(block for block in reference_sequence.controlled_blocks
                  if block.node_name == b"Bip01 NonAccum")
    original = source.interpolator
    if not isinstance(original, N.NiTransformInterpolator):
        raise TypeError("Forward visual anchor must be a transform interpolator")
    interp = N.NiTransformInterpolator()
    translation = original.translation
    quat = original.rotation
    if original.data is not None:
        if original.data.translations.num_keys:
            translation = original.data.translations.keys[0].value
        if original.data.num_rotation_keys:
            if original.data.rotation_type == 4:
                raise ValueError("Euler anchor sampling is not supported")
            quat = original.data.quaternion_keys[0].value
    interp.translation.x = translation.x
    interp.translation.y = translation.y
    interp.translation.z = translation.z
    set_quaternion(interp.rotation, (quat.w, quat.x, quat.y, quat.z))
    interp.scale = original.scale
    controlled = N.ControllerLink()
    controlled.interpolator = interp
    controlled.priority = 30
    controlled.node_name = b"Bip01 NonAccum"
    controlled.controller_type = b"NiTransformController"
    return controlled


def build_sequence(group_name, action, nodes, root_blocks, duration):
    frames = action["frames"]
    if len(frames) < 2:
        raise ValueError(f"{group_name}: action has fewer than two frames")
    animated_names = list(frames[0])
    if set(animated_names) != set(frames[-1]):
        raise ValueError(f"{group_name}: inconsistent animated bone set")

    output = N.Data(version=0x14020007, user_version=11, user_version_2=34)
    output.header.endian_type = 1
    sequence = N.NiControllerSequence()
    sequence.name = group_name.encode()
    sequence.weight = 1.0
    sequence.cycle_type = 0
    sequence.frequency = 1.0
    sequence.start_time = 0.0
    sequence.stop_time = duration
    sequence.target_name = b"Bip01"
    sequence.unknown_int_1 = 1

    text_keys = N.NiTextKeyExtraData()
    text_keys.num_text_keys = 3
    text_keys.text_keys.update_size()
    text_keys.text_keys[0].time, text_keys.text_keys[0].value = 0.0, b"start"
    text_keys.text_keys[1].time = min(duration, 1.0 / 30.0)
    text_keys.text_keys[1].value = b"Blend:9"
    text_keys.text_keys[2].time, text_keys.text_keys[2].value = duration, b"end"
    sequence.text_keys = text_keys

    blocks = list(root_blocks)
    blocks.extend(make_transform_block(name, nodes[name], frames, duration) for name in animated_names)
    sequence.num_controlled_blocks = len(blocks)
    sequence.controlled_blocks.update_size()
    for destination, source in zip(sequence.controlled_blocks, blocks):
        destination.interpolator = source.interpolator
        destination.priority = source.priority
        destination.node_name = source.node_name
        destination.controller_type = source.controller_type
    output.roots = [sequence]
    return output


def validate(path, expected_group, expected_frames, expect_root):
    data = read_nif(path)
    sequence = data.roots[0]
    if sequence.name != expected_group.encode():
        raise AssertionError((sequence.name, expected_group))
    blocks = {text(block.node_name): block for block in sequence.controlled_blocks}
    if ("Bip01" in blocks) != expect_root:
        raise AssertionError(f"{path.name}: unexpected root-controller state")
    if "Bip01 NonAccum" not in blocks:
        raise AssertionError(f"{path.name}: missing visual anchor")
    animated = [
        block for block in sequence.controlled_blocks
        if isinstance(block.interpolator, N.NiTransformInterpolator)
        and block.interpolator.data is not None
        and block.node_name not in (b"Bip01", b"Bip01 NonAccum")
    ]
    if len(animated) != 23:
        raise AssertionError(f"{path.name}: expected 23 retarget bones, got {len(animated)}")
    for block in animated:
        if block.interpolator.data.num_rotation_keys != expected_frames:
            raise AssertionError(f"{path.name}: lost rotation keys for {text(block.node_name)}")
    return len(sequence.controlled_blocks), sequence.stop_time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retarget", type=Path, required=True)
    parser.add_argument("--skeleton", type=Path, default=ROOT / "MO2/mods/NV Compatibility Skeleton/Meshes/Characters/_Male/Skeleton.nif")
    parser.add_argument("--source", type=Path, default=ROOT / "MO2/mods/Mojave Skate/meshes/MojaveSkate/locomotion")
    parser.add_argument("--output", type=Path, default=HERE / "generated/skate3-retarget/locomotion")
    args = parser.parse_args()

    payload = json.loads(args.retarget.resolve(strict=True).read_text(encoding="utf-8"))
    skeleton = read_nif(args.skeleton.resolve(strict=True))
    nodes = {}
    for block in skeleton.roots[0].tree():
        name = text(getattr(block, "name", ""))
        if name:
            nodes[name] = block
    required = set(payload["mapping"].values())
    missing = sorted(required - set(nodes))
    if missing:
        raise KeyError(f"skeleton lacks retarget bones: {missing}")

    args.output.mkdir(parents=True, exist_ok=True)
    report = {"schema": 2, "source": str(args.retarget), "files": {}}
    anchor_sequence = read_nif(args.source / "mtfastforward.kf").roots[0]
    build_sets = {args.output.name: (args.output, GROUPS)}
    build_sets.update({name: (args.output.parent / name, groups) for name, groups in CARVE_GROUPS.items()})
    for set_name, (output_dir, groups) in build_sets.items():
        output_dir.mkdir(parents=True, exist_ok=True)
        for stem, (group_name, action_names, keep_root) in groups.items():
            action = assemble_cycle(payload["actions"], action_names)
            source = read_nif((args.source / f"{stem}.kf").resolve(strict=True))
            source_sequence = source.roots[0]
            root_blocks = [
                block for block in source_sequence.controlled_blocks
                if block.node_name in (b"Bip01", b"Bip01 NonAccum")
            ] if keep_root else [stationary_nonaccum(anchor_sequence)]
            if keep_root and {block.node_name for block in root_blocks} != {b"Bip01", b"Bip01 NonAccum"}:
                raise AssertionError(f"{set_name}/{stem}: known-good root controllers were not found")
            duration = float(source_sequence.stop_time) if keep_root else (len(action["frames"]) - 1) / float(action["fps"])
            built = build_sequence(group_name, action, nodes, root_blocks, duration)
            destination = output_dir / f"{stem}.kf"
            with destination.open("wb") as stream:
                built.write(stream)
            blocks, stop_time = validate(destination, group_name, len(action["frames"]), keep_root)
            relative_name = destination.relative_to(args.output.parent).as_posix()
            report["files"][relative_name] = {
                "group": group_name,
                "actions": list(action_names),
                "frames": len(action["frames"]),
                "duration": stop_time,
                "controlled_blocks": blocks,
                "root_motion_preserved": keep_root,
            }
            print(f"VALID {relative_name}: {' + '.join(action_names)}, {len(action['frames'])} frames, {blocks} blocks")

    report_path = args.output.parent / "validation.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"WROTE {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

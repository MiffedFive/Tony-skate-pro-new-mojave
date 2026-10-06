"""Static private-build audit; --record updates hashes, never playtest claims.

No archives are built: installed donor-derived KFs are local test data.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from build_retargeted_kf import read_nif, text, ROOT

MOD = ROOT / "MO2/mods/Mojave Skate"
HERE = Path(__file__).resolve().parent


def audit():
    lengths = []
    for path in (MOD / "NVSE/Plugins/Scripts").glob("*.txt"):
        payload = path.read_bytes()
        assert len(payload) < 16384, path.name
        assert max(map(len, payload.splitlines())) < 512, path.name
        source = payload.decode("ascii")
        stack = []
        for token in re.finditer(r"\(Begin Function \{\}|End\)", source, re.I):
            if token.group().lower().startswith("(begin"):
                stack.append(token.start())
            else:
                lengths.append(token.end() - stack.pop())
        assert not stack, path.name
        blocks = []
        for line in source.splitlines():
            line = line.strip().lower()
            if line.startswith("if "): blocks.append("if")
            elif line.startswith("while "): blocks.append("while")
            elif line == "endif": assert blocks.pop() == "if", path.name
            elif line == "loop": assert blocks.pop() == "while", path.name
        assert not blocks, path.name
    assert max(lengths) < 480, max(lengths)
    main = (MOD / "NVSE/Plugins/Scripts/ln_MojaveSkate.txt").read_text("ascii")
    assert "CallWhile" not in main
    assert main.count("End) 1 1 9") == 18
    assert 'while msInit < 29' in main
    for variant in ("carve_left", "carve_right", "locomotion"):
        for enable in (0, 1):
            assert f'SetActorAnimationPath 0 {enable} "MojaveSkate\\{variant}"' in main
    ET.parse(MOD / "menus/prefabs/MojaveSkate/hud.xml")
    count = 0
    for folder, expected in (("locomotion", 11), ("carve_left", 3), ("carve_right", 3)):
        paths = sorted((MOD / "meshes/MojaveSkate" / folder).glob("*.kf"))
        assert len(paths) == expected, (folder, len(paths))
        for path in paths:
            sequence = read_nif(path).roots[0]
            blocks = {text(b.node_name): b for b in sequence.controlled_blocks}
            assert "Bip01 NonAccum" in blocks, (path, "missing visual anchor")
            stationary = path.stem in ("mtidle", "mtturnleft", "mtturnright")
            assert ("Bip01" in blocks) != stationary, (path, "root-motion mismatch")
            assert len(blocks) == (24 if stationary else 25), path
            assert sequence.stop_time > sequence.start_time
            assert sequence.text_keys.text_keys[-1].value == b"end"
            if stationary:
                anchor = blocks["Bip01 NonAccum"].interpolator
                assert 55 < anchor.translation.z < 70, (path, "wrong runtime height")
            count += 1
    baseline = HERE / "backups/confirmed-skate3-push-2026-10-04/Mojave Skate"
    for name in ("mtforward.kf", "mtfastforward.kf"):
        relative = Path("meshes/MojaveSkate/locomotion") / name
        assert (MOD / relative).read_bytes() == (baseline / relative).read_bytes(), name
    return {"main_loop_callbacks": 18, "inline_functions": len(lengths),
            "max_lambda_chars": max(lengths), "locomotion_kfs_checked": count,
            "forward_baseline_hash_match": True, "stationary_runtime_anchor": True,
            "xml": "well-formed", "packaging": "disabled: private donor-derived KFs"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    checked = audit()
    if args.record:
        path = HERE / "VALIDATION.json"
        report = json.loads(path.read_text("utf-8"))
        report["static_audit"] = checked
        report["files"] = {str(p.relative_to(MOD)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(MOD.rglob("*")) if p.is_file()}
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checked, indent=2))


if __name__ == "__main__":
    main()

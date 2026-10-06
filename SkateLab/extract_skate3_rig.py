#!/usr/bin/env python3
"""Extract the verified default Skate 3 skater RX2 set from owned game data.

Only source tooling and hashes belong in this workspace. Point ``--output`` at
an external private directory; the extracted retail assets must not be shipped
with Mojave Skate.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--tool-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    archive_path = args.archive.resolve(strict=True)
    manifest_path = args.manifest.resolve(strict=True)
    tool_root = args.tool_root.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to use non-empty output directory: {output}")

    sys.path.insert(0, str(tool_root))
    BigArchive = importlib.import_module("tools.owned_game.big").BigArchive

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_archive_size = int(manifest["archive"]["size"])
    if archive_path.stat().st_size != expected_archive_size:
        raise ValueError(
            f"archive size mismatch: {archive_path.stat().st_size} != "
            f"{expected_archive_size}"
        )

    archive = BigArchive(archive_path)
    entries = {entry.path.lower(): entry for entry in archive.entries}
    written: list[dict[str, object]] = []
    for component in manifest["components"]:
        slot = component["slot"]
        model_id = component["model_id"]
        archive_name = (
            f"data/content/createacharacter/model/cas_db/{slot}/"
            f"0x{model_id}.rx2"
        )
        entry = entries.get(archive_name.lower())
        if entry is None:
            raise FileNotFoundError(f"archive entry is missing: {archive_name}")

        payload = archive.read(entry)
        actual_hash = sha256_bytes(payload)
        expected_hash = manifest["model_sha256"][model_id]
        if actual_hash != expected_hash:
            raise ValueError(
                f"{slot} hash mismatch: {actual_hash} != {expected_hash}"
            )

        target = output / slot / f"0x{model_id}.rx2"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        written.append(
            {
                "slot": slot,
                "path": str(target),
                "bytes": len(payload),
                "sha256": actual_hash,
            }
        )

    print(json.dumps({"ok": True, "models": written}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

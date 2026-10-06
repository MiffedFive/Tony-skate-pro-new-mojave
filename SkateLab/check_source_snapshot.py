"""Audit the source-only publication without executing the mod or build tools.

Run: python SkateLab/check_source_snapshot.py
No game files, installed dependencies or network access are needed.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
META = {
    ".gitignore", ".gitattributes", "README.md", "DEVELOPMENT.md",
    "COPYRIGHT.md", "SOURCE_MANIFEST.json", "SkateLab/check_source_snapshot.py",
}
SECRET_PATTERNS = (
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}",
    r"AKIA[A-Z0-9]{16}",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
)


def main() -> int:
    manifest = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["files"]}
    allowed = set(entries) | META
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(ROOT).parts
    }
    errors = []
    for path in sorted(actual - allowed):
        errors.append(f"unexpected file: {path}")
    for path in sorted(allowed - actual):
        errors.append(f"missing file: {path}")

    checked_python = 0
    for relative in sorted(actual & allowed):
        path = ROOT / relative
        payload = path.read_bytes()
        if relative in entries:
            entry = entries[relative]
            if len(payload) != entry["bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                errors.append(f"snapshot hash/size mismatch: {relative}")
        if path.suffix.lower() == ".dds":
            if not relative.startswith("MO2/mods/Mojave Skate/textures/MojaveSkate/") or payload[:4] != b"DDS ":
                errors.append(f"unapproved binary asset: {relative}")
            continue
        try:
            content = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            errors.append(f"non-text file: {relative}")
            continue
        if any(re.search(pattern, content) for pattern in SECRET_PATTERNS):
            errors.append(f"possible credential in {relative} (value suppressed)")
        if re.search(r"[A-Za-z]:[\\/](?:Users|dowloands|Skate3-)", content, re.IGNORECASE):
            errors.append(f"private machine path: {relative}")
        if path.suffix == ".py":
            try:
                ast.parse(content, filename=relative)
                checked_python += 1
            except SyntaxError:
                errors.append(f"Python syntax error: {relative}")

    runtime = ROOT / "MO2/mods/Mojave Skate/NVSE/Plugins/Scripts/ln_MojaveSkate.txt"
    if runtime.exists():
        script = runtime.read_text(encoding="utf-8-sig")
        if script.count("SetGameMainLoopCallback") != 18:
            errors.append("unexpected main-loop callback count")
        if len(runtime.read_bytes()) >= 16384:
            errors.append("runtime exceeds script size budget")

    if errors:
        print("FAIL\n" + "\n".join(errors))
        return 1
    print(f"PASS: {len(actual)} allowlisted files; {len(entries)} original hashes; {checked_python} Python syntax checks.")
    print("Source-only audit; not an in-game test or a full credential/provenance guarantee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

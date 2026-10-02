"""Reuse source timestamps only when exact contents, mode and cache root match."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def scan(root):
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in {"target", ".git", ".zig-cache"}
                   and not (Path(directory) / d).is_symlink()]
        for name in names:
            p = Path(directory) / name
            if p.is_file() and not p.is_symlink():
                yield p


def apply(action, roots, state):
    if action == "restore":
        if not state.exists():
            print("No content-verified timestamp snapshot yet; normal Cargo freshness checks apply")
            return
        saved = json.loads(state.read_text())
        if saved.get("roots") != {k: str(v) for k, v in roots.items()}:
            print("Cache input roots differ; retaining fresh timestamps")
            return
    else:
        saved = {"roots": {k: str(v) for k, v in roots.items()}, "files": {}}
    count = 0
    for label, root in roots.items():
        for p in scan(root):
            key = label + "/" + p.relative_to(root).as_posix()
            stat = p.stat()
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            mode = stat.st_mode & 0o777
            if action == "capture":
                saved["files"][key] = {"sha256": digest, "mode": mode, "mtime_ns": stat.st_mtime_ns}
                count += 1
            else:
                old = saved["files"].get(key)
                if old and old["sha256"] == digest and old["mode"] == mode:
                    os.utime(p, ns=(stat.st_atime_ns, old["mtime_ns"]))
                    count += 1
    if action == "capture":
        state.write_text(json.dumps(saved, sort_keys=True) + "\n")
    print(f"{action}: {count} source inputs verified by SHA256 and mode")


if __name__ == "__main__":
    action, source, snapshot = sys.argv[1:]
    assert action in {"capture", "restore"}
    sysroot = Path(subprocess.check_output(["rustc", "--print", "sysroot"], text=True).strip())
    roots = {"codex": Path(source).resolve(), "rust": sysroot / "lib/rustlib/src/rust/library"}
    assert all(root.is_dir() for root in roots.values())
    apply(action, roots, Path(snapshot))

import os
from pathlib import Path

SKIP_DIRS = {
    "Library",
    "node_modules",
    "__pycache__",
    "venv",
    "Pods",
    "DerivedData",
}


def get_filetree_mac() -> dict:
    root = Path.home()
    paths = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in place before descending.
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in SKIP_DIRS
        ]

        rel_dir = Path(dirpath).relative_to(root)

        for d in dirnames:
            paths.append(f"{(rel_dir / d).as_posix()}/")

        for f in filenames:
            if f.startswith("."):
                continue
            paths.append((rel_dir / f).as_posix())

    return {"root": str(root), "paths": sorted(paths)}

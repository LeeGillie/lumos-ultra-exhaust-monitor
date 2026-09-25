"""Copy the node firmware to a board on USB with mpremote, then reset it.

    python tools/upload.py                 # first USB serial port found
    python tools/upload.py --port COM8
    python tools/upload.py --no-reset      # leave it at the REPL
    python tools/upload.py --config config_fan.py --port COM8

Copies lib/, the box's config and main.py, skipping __pycache__. main.py goes
last so a half-finished upload never boots a mix of old and new code.

Each box keeps its own git-ignored config on the PC (config_laser.py,
config_fan.py, ...); --config picks one and it lands on the board as config.py,
which is the only name main.py reads. Without --config, config.py is used if it
exists; with several config_*.py files and no choice made, nothing is uploaded.
"""

import argparse
import re
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MKDIRS = """import os
for d in {dirs!r}:
    try:
        os.mkdir(d)
    except OSError:
        pass
"""


def mpremote() -> list:
    if importlib.util.find_spec("mpremote"):
        return [sys.executable, "-m", "mpremote"]
    exe = shutil.which("mpremote")
    if exe:
        return [exe]
    sys.exit(f"mpremote not found for {sys.executable} or on PATH — pip install mpremote")


def pick_config(choice) -> Path:
    if choice:
        path = Path(choice)
        path = path if path.is_absolute() or path.exists() else ROOT / path
        if not path.exists():
            sys.exit(f"{choice} not found")
        return path
    if (ROOT / "config.py").exists():
        return ROOT / "config.py"
    boxes = sorted(p.name for p in ROOT.glob("config_*.py") if p.name != "config_example.py")
    if boxes:
        sys.exit("which box? pass --config with one of: " + ", ".join(boxes))
    print("no config found - uploading config_example.py; the node will run with that")
    return ROOT / "config_example.py"


def node_id(config: Path) -> str:
    m = re.search(r'^NODE_ID\s*=\s*["\']([^"\']+)', config.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "?"


def files(config: Path) -> list:
    """(source, destination on the board) pairs, main.py last."""
    lib = [p for p in sorted((ROOT / "lib").rglob("*.py")) if "__pycache__" not in p.parts]
    return ([(p, p.relative_to(ROOT).as_posix()) for p in lib]
            + [(config, "config.py"), (ROOT / "main.py", "main.py")])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default="auto", help="COM8, /dev/ttyUSB0 … (default: auto)")
    ap.add_argument("--no-reset", action="store_true", help="don't reset after copying")
    ap.add_argument("--config", help="this box's config, e.g. config_fan.py (sent as config.py)")
    args = ap.parse_args()

    config = pick_config(args.config)
    todo = files(config)
    dirs = sorted({d.rsplit("/", 1)[0] for _, d in todo if "/" in d})
    dirs = sorted({"/".join(d.split("/")[:i + 1]) for d in dirs for i in range(d.count("/") + 1)})

    cmd = mpremote() + ["connect", args.port, "exec", MKDIRS.format(dirs=dirs)]
    for src, dest in todo:
        cmd += ["+", "fs", "cp", str(src), ":" + dest]
    if not args.no_reset:
        cmd += ["+", "reset"]

    print(f"config: {config.name} -> :config.py (NODE_ID '{node_id(config)}')")
    print(f"uploading {len(todo)} files to {args.port}")
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()

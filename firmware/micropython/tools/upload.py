"""Copy the node firmware to a board on USB with mpremote, then reset it.

    python tools/upload.py                 # first USB serial port found
    python tools/upload.py --port COM8
    python tools/upload.py --no-reset      # leave it at the REPL

Copies lib/, config.py (or config_example.py if there is none) and main.py,
skipping __pycache__. main.py goes last so a half-finished upload never boots
a mix of old and new code.
"""

import argparse
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


def files() -> list:
    lib = [p for p in sorted((ROOT / "lib").rglob("*.py")) if "__pycache__" not in p.parts]
    config = ROOT / "config.py"
    if not config.exists():
        print("config.py not found — uploading config_example.py; the node will run with that")
        config = ROOT / "config_example.py"
    return lib + [config, ROOT / "main.py"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default="auto", help="COM8, /dev/ttyUSB0 … (default: auto)")
    ap.add_argument("--no-reset", action="store_true", help="don't reset after copying")
    args = ap.parse_args()

    todo = files()
    dirs = sorted({p.parent.relative_to(ROOT).as_posix() for p in todo if p.parent != ROOT})
    dirs = sorted({"/".join(d.split("/")[:i + 1]) for d in dirs for i in range(d.count("/") + 1)})

    cmd = mpremote() + ["connect", args.port, "exec", MKDIRS.format(dirs=dirs)]
    for p in todo:
        cmd += ["+", "fs", "cp", str(p), ":" + p.relative_to(ROOT).as_posix()]
    if not args.no_reset:
        cmd += ["+", "reset"]

    print(f"uploading {len(todo)} files to {args.port}")
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()

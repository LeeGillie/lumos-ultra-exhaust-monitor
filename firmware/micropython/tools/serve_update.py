"""Serve this folder to the nodes for over-the-air updates.

    python tools/serve_update.py [--port 8123]

Writes manifest.json (file list + SHA-256) and serves the folder over HTTP.
Then send {"cmd":"update"} to a node — from the LumosAir app, or:

    python tools/send_command.py laser update
"""

import argparse
import hashlib
import http.server
import json
import os
import socket
import socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE_SUFFIX = {".py"}
SKIP = {"config.py", "manifest.json", "tools", "tests", "out"}


def build_manifest() -> dict:
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in INCLUDE_SUFFIX:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(rel == s or rel.startswith(s + "/") for s in SKIP):
            continue
        files.append({"path": rel,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "bytes": path.stat().st_size})
    return {"files": files}


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8123)
    args = ap.parse_args()

    manifest = build_manifest()
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"manifest.json: {len(manifest['files'])} files")

    os.chdir(ROOT)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", args.port), handler) as httpd:
        url = f"http://{local_ip()}:{args.port}"
        print(f"serving {ROOT} at {url}")
        print(f'set OTA_URL = "{url}" in config.py, then send {{"cmd":"update"}}')
        httpd.serve_forever()


if __name__ == "__main__":
    main()

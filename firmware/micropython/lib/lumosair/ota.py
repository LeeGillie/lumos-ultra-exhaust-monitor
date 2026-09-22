"""Wi-Fi update: pull new files from a small HTTP server on the PC.

On the PC, from the firmware/micropython folder:

    python tools/serve_update.py          # writes manifest.json and serves the folder

Then from the app (or any UDP tool) send {"cmd":"update"} to the node. The node
fetches manifest.json, downloads only the files whose SHA-256 differs, writes
them, and reboots. No cable, no pulling the box off the duct.
"""

import json
import os
import socket

try:
    import hashlib
    import binascii
except ImportError:                                   # pragma: no cover
    hashlib = None
    binascii = None


def _get(url, chunk_cb=None, timeout=10):
    """Minimal HTTP GET. Returns the body as bytes when no callback is given."""
    proto, _, host_port, path = url.split("/", 3)
    path = "/" + path
    host, _, port = host_port.partition(":")
    port = int(port or (443 if proto == "https:" else 80))
    if proto == "https:":
        raise ValueError("plain http only")
    addr = socket.getaddrinfo(host, port)[0][-1]
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect(addr)
        s.send(("GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n"
                % (path, host_port)).encode())
        buf = b""
        header_done = False
        out = bytearray()
        while True:
            data = s.recv(512)
            if not data:
                break
            if not header_done:
                buf += data
                idx = buf.find(b"\r\n\r\n")
                if idx < 0:
                    continue
                status = int(buf.split(b" ")[1])
                if status != 200:
                    raise OSError("http %d" % status)
                header_done = True
                data = buf[idx + 4:]
            if not data:
                continue
            if chunk_cb:
                chunk_cb(data)
            else:
                out += data
        return bytes(out)
    finally:
        s.close()


def _sha256_file(path):
    if hashlib is None:
        return ""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                b = f.read(512)
                if not b:
                    break
                h.update(b)
        return binascii.hexlify(h.digest()).decode()
    except OSError:
        return ""


def _mkdirs(path):
    parts = path.split("/")[:-1]
    cur = ""
    for p in parts:
        if not p:
            continue
        cur += "/" + p if cur else p
        try:
            os.mkdir(cur)
        except OSError:
            pass


def update(base_url, log=print):
    """Returns the number of files written. Reboot afterwards to run them."""
    base = base_url.rstrip("/")
    log("ota: fetching manifest from", base)
    manifest = json.loads(_get(base + "/manifest.json"))
    written = 0
    for entry in manifest.get("files", []):
        name, want = entry["path"], entry.get("sha256", "")
        if _sha256_file(name) == want and want:
            continue
        log("ota:", name)
        _mkdirs(name)
        tmp = name + ".new"
        with open(tmp, "wb") as f:
            _get(base + "/" + name, chunk_cb=f.write)
        got = _sha256_file(tmp)
        if want and got != want:
            os.remove(tmp)
            raise OSError("checksum mismatch for " + name)
        try:
            os.remove(name)
        except OSError:
            pass
        os.rename(tmp, name)
        written += 1
    log("ota: %d file(s) updated" % written)
    return written

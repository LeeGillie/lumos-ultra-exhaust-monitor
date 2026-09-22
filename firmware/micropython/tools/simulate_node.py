"""Run a node on the PC, with its display rendered to a PNG.

    python tools/simulate_node.py                       # every scenario -> out/
    python tools/simulate_node.py --scenario binleak
    python tools/simulate_node.py --live                # act as a real node on the LAN

There is no hardware in this, and no mock of the UI either: it imports the real
lumosair.st7789 and lumosair.display_ui and decodes the SPI command stream the
driver emits (CASET / RASET / RAMWR) into a framebuffer. What you see is what
the panel would show, pixel for pixel, including every layout bug.

Standalone mode paints a set of scenarios and writes PNGs. --live turns it into
a stand-in for a real box: it publishes telemetry on UDP 47810, accepts commands
on 47811 and listens for the desktop app's status broadcast on 47812, so you can
run the app with Source = Udp and watch the box screen react. Ctrl+C to stop.

Only stdlib. The 8x8 font below stands in for MicroPython's built-in one - same
fixed 8x8 cell, so anything that fits here fits on the panel.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import socket
import struct
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT))

_FONT8 = base64.b64decode(
    "AAAAAAAAAAAMDAwMCAAMAAwMDAAAAAAAFBQ+BD8KCgAAHgIOGBAeAAYFFgwaKBgADAIGLjkTPgAACAgAAAAAAAgE"
    "BAQEBAgIBAgICAgIBAQSDAwSAAAAAAAAAD8AAAAAAAAAAAAADAwAAAAADAAAAAAAAAAAAAwAEBAICAQEAgIMEhIe"
    "EhIMAA4ICAgICB4ADhIQCAQCHgAOEhAMEBAeABgcEBI/EBAAHgIOEBAQDgAcAgIeEhIcAB4QGAgIBAQAHhISHBIS"
    "HgAOEhIeEBAOAAAADAAAAAwAAAAMAAAADAwAMAwDDDAAAAAAPwA/AAAAAAMMMAwDAAAeEBgIBAAEABwiOSUlJTkC"
    "DAwEEh4SIQAeEhIeEjIeABwCAgICAhwADhISEhISDgAeAgIeAgIeAD4CAh4CAgIAHAICGxISHAASEhIeEhISAB4M"
    "DAwMDB4AHBAQEBAYDgASCg4OChIyAAICAgICAj4AMzMtLSEhIQASFhYSGhoSAAwSEhISEgwAHjIyHgICAgAMEhIS"
    "EhIcEB4SEg4SEiIADhICDBASHgA/DAwMDAwMABISEhISEh4AIRISEgwMDAAhIS0tHhISADISDAwMEiMAMxIMDAwM"
    "DAA+EAgIBAI+AAQEBAQEBAQMAgIEBAgIEBAICAgICAgIDAweEgAAAAAAAAAAAAAAAD4EAAAAAAAAAAAAHhAeEh4A"
    "AgIeEhISHgAAABwCAgIcABAQHhISEh4AAAAcEh4CHAAMBB4EBAQEAAAAHhISEh4QAgIeEhISEgAAAA4ICAgeAAAA"
    "DggICAgIAgISCg4SMgAEBAQEBAQYAAAAHy8pKSkAAAAeEhISEgAAAB4SEhIeAAAAHhISEh4CAAAeEhISHhAAADwE"
    "BAQEAAAAHgIMEB4ABAQeBAQEHAAAABISEhIeAAAAEhISDAwAAAAhIR4eEgAAABIMDAwSAAAAEhIUDAwEAAAeAAAA"
    "HgAICAQGBAgIGAAICAgICAgIBAQIGAgEBAYAAAAGGAAAAA=="
)

# ======================================================================================
# a minimal `framebuf` so the real driver's text() path works off-target
# ======================================================================================
class _FrameBuffer:
    """Just enough of MicroPython's framebuf.FrameBuffer for st7789.text()."""

    def __init__(self, buf, w, h, fmt=None):
        self.buf, self.w, self.h = buf, w, h

    def _set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 2
            self.buf[i] = (c >> 8) & 0xFF
            self.buf[i + 1] = c & 0xFF

    def pixel(self, x, y, c=None):
        if c is not None:
            self._set(x, y, c)
            return None
        if not (0 <= x < self.w and 0 <= y < self.h):
            return 0
        i = (y * self.w + x) * 2
        return (self.buf[i] << 8) | self.buf[i + 1]

    def fill(self, c):
        for y in range(self.h):
            for x in range(self.w):
                self._set(x, y, c)

    def fill_rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._set(xx, yy, c)

    def text(self, s, x, y, c=0xFFFF):
        for i, ch in enumerate(s):
            o = ord(ch)
            if not (32 <= o <= 126):
                o = 63                                   # '?'
            g = _FONT8[(o - 32) * 8:(o - 32) * 8 + 8]
            for row in range(8):
                bits = g[row]
                for col in range(8):
                    if bits & (1 << col):
                        self._set(x + i * 8 + col, y + row, c)


class _FramebufModule:
    FrameBuffer = _FrameBuffer
    RGB565 = 1


from lumosair import display_ui, st7789           # noqa: E402

# st7789 guards `import framebuf`, `from machine import Pin` and `from time import
# sleep_ms` in ONE try block, so on a PC the two hardware imports fail and framebuf
# is nulled with them — text() then returns immediately and draws nothing. Hand the
# driver a working framebuf back; it doesn't touch the other two unless you pass it
# rst/bl pins, which we don't.
st7789.framebuf = _FramebufModule()


# ======================================================================================
# the virtual panel: decode what the driver actually sends
# ======================================================================================
class _Pin:
    def __init__(self, v=0):
        self._v = v

    def value(self, v=None):
        if v is None:
            return self._v
        self._v = v


class VirtualPanel:
    """Fake SPI that reassembles the ST7789 command stream into a framebuffer."""

    def __init__(self, width=320, height=240):
        self.w, self.h = width, height
        self.fb = bytearray(width * height * 2)
        self.dc = _Pin(1)
        self.cs = _Pin(1)
        self._cmd = None
        self._args = bytearray()
        self.x0 = self.x1 = self.y0 = self.y1 = 0
        self.cx = self.cy = 0
        self.writing = False
        self.pixels_written = 0

    # -- SPI ------------------------------------------------------------------
    def write(self, data):
        if self.dc.value() == 0:                          # command byte
            self._finish()
            self._cmd = data[0]
            self._args = bytearray()
            if self._cmd == 0x2C:                         # RAMWR: pixels follow
                self.writing = True
                self.cx, self.cy = self.x0, self.y0
            return
        if self.writing and self._cmd == 0x2C:
            self._pixels(data)
        else:
            self._args.extend(data)

    def _finish(self):
        if self._cmd == 0x2A and len(self._args) >= 4:     # column address set
            self.x0 = (self._args[0] << 8) | self._args[1]
            self.x1 = (self._args[2] << 8) | self._args[3]
        elif self._cmd == 0x2B and len(self._args) >= 4:   # row address set
            self.y0 = (self._args[0] << 8) | self._args[1]
            self.y1 = (self._args[2] << 8) | self._args[3]
        self._cmd = None
        self._args = bytearray()

    def _pixels(self, data):
        # The driver writes RGB565 already byte-swapped for the panel; undo that
        # here so the PNG comes out the right colour.
        for i in range(0, len(data) - 1, 2):
            lo, hi = data[i], data[i + 1]
            if self.x0 <= self.cx < self.w and self.y0 <= self.cy < self.h:
                j = (self.cy * self.w + self.cx) * 2
                self.fb[j] = hi
                self.fb[j + 1] = lo
                self.pixels_written += 1
            self.cx += 1
            if self.cx > self.x1:
                self.cx = self.x0
                self.cy += 1
                if self.cy > self.y1:
                    self.writing = False
                    return

    # -- output ---------------------------------------------------------------
    def rgb_rows(self, scale=1):
        rows = []
        for y in range(self.h):
            row = bytearray()
            for x in range(self.w):
                j = (y * self.w + x) * 2
                v = (self.fb[j] << 8) | self.fb[j + 1]
                r = ((v >> 11) & 0x1F) * 255 // 31
                g = ((v >> 5) & 0x3F) * 255 // 63
                b = (v & 0x1F) * 255 // 31
                row += bytes((r, g, b)) * scale
            for _ in range(scale):
                rows.append(bytes(row))
        return rows

    def save_png(self, path, scale=2):
        rows = self.rgb_rows(scale)
        raw = b"".join(b"\x00" + r for r in rows)
        w, h = self.w * scale, self.h * scale

        def chunk(tag, data):
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw, 9))
               + chunk(b"IEND", b""))
        Path(path).write_bytes(png)
        return path


# ======================================================================================
# scenarios — what the box shows in each situation worth looking at
# ======================================================================================
# (name, severity, cfm, source, fan level, mode, recommended, headline, channels)
LASER_CH = ["cyc_dp", "bin", "pitot", "run_in", "encl"]
FAN_CH = ["fan_in"]

SCENARIOS = {
    "healthy": dict(
        sev="ok", cfm=212, src="pitot", level=7, mode="auto", rec=7,
        head="Everything within baseline",
        ch=[("cyc_dp", 168.4, True), ("bin", -42.1, True), ("pitot", 61.8, True),
            ("run_in", -96.3, True), ("encl", -18.9, True)]),
    "clog": dict(
        sev="critical", cfm=118, src="taps (pitot suspect)", level=10, mode="auto", rec=10,
        head="Long run restricted - check for a kink",
        ch=[("cyc_dp", 61.2, True), ("bin", -18.7, True), ("pitot", 19.4, True),
            ("run_in", -188.5, True), ("encl", -7.1, True)]),
    "binleak": dict(
        sev="warning", cfm=198, src="pitot", level=7, mode="auto", rec=8,
        head="Dust bin appears to be leaking",
        ch=[("cyc_dp", 151.0, True), ("bin", -6.2, True), ("pitot", 57.1, True),
            ("run_in", -92.8, True), ("encl", -17.4, True)]),
    "pitot": dict(
        sev="warning", cfm=205, src="taps (pitot suspect)", level=7, mode="auto", rec=7,
        head="Pitot disagrees - tip may be blocked",
        ch=[("cyc_dp", 164.9, True), ("bin", -41.0, True), ("pitot", 8.2, True),
            ("run_in", -95.0, True), ("encl", -18.2, True)]),
    "slow": dict(
        sev="advice", cfm=96, src="pitot", level=3, mode="manual", rec=8,
        head="Raise the fan to 8 for brass",
        ch=[("cyc_dp", 39.8, True), ("bin", -11.9, True), ("pitot", 13.0, True),
            ("run_in", -38.4, True), ("encl", -6.6, True)]),
    "sensorfault": dict(
        sev="warning", cfm=203, src="taps", level=7, mode="auto", rec=7,
        head="encl channel not responding",
        ch=[("cyc_dp", 166.1, True), ("bin", -41.6, True), ("pitot", 60.2, True),
            ("run_in", -95.5, True), ("encl", 0.0, False)]),
    "nopc": dict(
        sev="stale", cfm=None, src="no PC link", level=None, mode="", rec=None,
        head="Desktop app not running",
        ch=[("cyc_dp", 167.2, True), ("bin", -41.8, True), ("pitot", 60.9, True),
            ("run_in", -95.9, True), ("encl", -18.5, True)]),
    "fannode": dict(
        sev="ok", cfm=212, src="pitot", level=7, mode="auto", rec=7,
        head="Everything within baseline",
        ch=[("fan_in", -214.6, True)], node="fan"),
}


def paint(panel, node_id, s, ip="192.168.1.42"):
    tft = st7789.ST7789(panel, panel.cs, panel.dc, rotation=1)
    tft.init()
    scr = display_ui.Screen(tft, node_id)
    scr.layout()
    scr.status(s["sev"], ip=ip)
    scr.flow(s["cfm"], s["src"])
    scr.fan(s["level"], s["mode"], s["rec"])
    scr.headline(s["head"], s["sev"])
    scr.channels(s["ch"])
    return scr


def run_scenarios(names, out_dir, scale):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        s = SCENARIOS[name]
        panel = VirtualPanel()
        t0 = time.time()
        paint(panel, s.get("node", "laser"), s)
        p = out_dir / ("screen_%s.png" % name)
        panel.save_png(p, scale)
        print("%-12s %6d px painted, %5.1f%% of the panel, %4.0f ms  -> %s"
              % (name, panel.pixels_written,
                 100.0 * panel.pixels_written / (panel.w * panel.h),
                 (time.time() - t0) * 1000, p))


# ======================================================================================
# live mode — behave like a real box on the LAN
# ======================================================================================
def run_live(node_id, out_dir, scale, period, telemetry_port, cmd_port, status_port):
    panel = VirtualPanel()
    tft = st7789.ST7789(panel, panel.cs, panel.dc, rotation=1)
    tft.init()
    scr = display_ui.Screen(tft, node_id)
    scr.splash("simulated node")
    time.sleep(0.4)
    scr.layout()

    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(("", status_port))
    rx.setblocking(False)
    cmd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cmd.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    cmd.bind(("", cmd_port))
    cmd.setblocking(False)

    names = FAN_CH if node_id == "fan" else LASER_CH
    base = {"cyc_dp": 168.0, "bin": -42.0, "pitot": 62.0,
            "run_in": -96.0, "encl": -19.0, "fan_in": -214.0}
    level, mode, rec, sev, cfm, src, head = 7, "manual", None, "stale", None, "no PC link", "Waiting for the desktop app"
    seq = 0
    last_status = 0.0
    png = out_dir / ("screen_live_%s.png" % node_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    print("simulated %s node: telemetry -> UDP %d, commands <- %d, status <- %d"
          % (node_id, telemetry_port, cmd_port, status_port))
    print("screen written to %s after every frame. Ctrl+C to stop." % png)

    try:
        while True:
            seq += 1
            wobble = math.sin(seq / 9.0)
            chans = {}
            for n in names:
                v = base[n] * (0.55 + 0.045 * level) * (1 + 0.012 * wobble)
                chans[n] = {"pa": round(v, 2), "t": 24.0, "ok": True}
            frame = {"node": node_id, "seq": seq, "up": seq * int(period * 1000),
                     "rssi": -61, "ch": chans,
                     "env": {"t": 23.9, "rh": 41.0, "p": 94412}}
            if node_id == "fan":
                frame["fan"] = level
            tx.sendto(json.dumps(frame).encode(), ("255.255.255.255", telemetry_port))

            try:                                          # commands from the app
                while True:
                    data, _ = cmd.recvfrom(2048)
                    m = json.loads(data.decode())
                    if m.get("cmd") == "set_level":
                        level = max(0, min(10, int(m.get("level", level))))
                        print("  <- set_level %d" % level)
                    else:
                        print("  <- %s" % m.get("cmd"))
            except (BlockingIOError, OSError, ValueError):
                pass

            try:                                          # status from the app
                while True:
                    data, _ = rx.recvfrom(2048)
                    m = json.loads(data.decode())
                    if m.get("t") != "status":
                        continue
                    sev = m.get("sev", "ok")
                    cfm = m.get("cfm")
                    src = m.get("src", "")
                    head = m.get("msg", "")
                    f = m.get("fan") or {}
                    mode = f.get("mode", mode)
                    rec = f.get("rec")
                    if f.get("level") is not None:
                        level = f["level"]
                    last_status = time.time()
            except (BlockingIOError, OSError, ValueError):
                pass

            if last_status and time.time() - last_status > 10:
                sev, cfm, src, head = "stale", None, "no PC link", "Desktop app not running"

            scr.status(sev, ip="192.168.1.42")
            scr.flow(cfm, src)
            scr.fan(level, mode, rec)
            scr.headline(head, sev)
            scr.channels([(n, chans[n]["pa"], True) for n in names])
            panel.save_png(png, scale)
            time.sleep(period)
    except KeyboardInterrupt:
        print("\nstopped")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS) + ["all"], default="all")
    ap.add_argument("--node", choices=["laser", "fan"], default="laser")
    ap.add_argument("--live", action="store_true", help="act as a real node on the LAN")
    ap.add_argument("--scale", type=int, default=2, help="PNG pixel scale")
    ap.add_argument("--period", type=float, default=1.0, help="live: seconds per frame")
    ap.add_argument("--udp", type=int, default=47810)
    ap.add_argument("--cmd-port", type=int, default=47811)
    ap.add_argument("--status-port", type=int, default=47812)
    ap.add_argument("--out", default=str(ROOT / "out"))
    a = ap.parse_args()
    out = Path(a.out)
    if a.live:
        run_live(a.node, out, a.scale, a.period, a.udp, a.cmd_port, a.status_port)
        return 0
    run_scenarios(sorted(SCENARIOS) if a.scenario == "all" else [a.scenario], out, a.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

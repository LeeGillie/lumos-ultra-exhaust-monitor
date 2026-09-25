"""Run a node on the PC, with its display rendered to a PNG.

    python tools/simulate_node.py                       # every scenario -> out/
    python tools/simulate_node.py --window              # ...in a window, arrows to browse
    python tools/simulate_node.py --live --window       # a live box, on screen
    python tools/simulate_node.py --live                # headless, PNG per frame

There is no hardware in this, and no mock of the UI either: it imports the real
lumosair.st7789 and lumosair.display_ui and decodes the SPI command stream the
driver emits (CASET / RASET / RAMWR) into a framebuffer. What you see is what
the panel would show, pixel for pixel, including every layout bug.

--window opens a real window (tkinter, stdlib) so you can watch it; without it the
panel is written to a PNG. Standalone mode paints a set of scenarios; --live turns it into
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
import os
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

# What each channel reads at each fan level, straight out of the desktop app's own
# physics model (SystemModel.PredictReading) for Option A and Option C. Made-up
# numbers look plausible but are not a solved operating point, so the taps disagree
# with each other and the app quite correctly flags the pitot as suspect.
_PROFILES = json.loads(
    "{\"A\":{\"0\":{\"fan/fan_in\":0,\"laser/bin\":0,\"laser/cyc_dp\":0,\"laser/encl\":0,\"laser/pitot\":"
    "0,\"laser/run_in\":0},\"1\":{\"fan/fan_in\":4.19,\"laser/bin\":2.5,\"laser/cyc_dp\":2.14,\"laser/"
    "encl\":0.18,\"laser/pitot\":0.44,\"laser/run_in\":3.59},\"10\":{\"fan/fan_in\":416.28,\"laser/bi"
    "n\":267.09,\"laser/cyc_dp\":228.21,\"laser/encl\":18.78,\"laser/pitot\":46.96,\"laser/run_in\":"
    "373.72},\"2\":{\"fan/fan_in\":16.71,\"laser/bin\":10.29,\"laser/cyc_dp\":8.79,\"laser/encl\":0.7"
    "2,\"laser/pitot\":1.81,\"laser/run_in\":14.59},\"3\":{\"fan/fan_in\":37.55,\"laser/bin\":23.44,\""
    "laser/cyc_dp\":20.03,\"laser/encl\":1.65,\"laser/pitot\":4.12,\"laser/run_in\":33.08},\"4\":{\"f"
    "an/fan_in\":66.71,\"laser/bin\":41.98,\"laser/cyc_dp\":35.87,\"laser/encl\":2.95,\"laser/pitot"
    "\":7.38,\"laser/run_in\":59.1},\"5\":{\"fan/fan_in\":104.19,\"laser/bin\":65.93,\"laser/cyc_dp\":"
    "56.33,\"laser/encl\":4.64,\"laser/pitot\":11.59,\"laser/run_in\":92.65},\"6\":{\"fan/fan_in\":14"
    "9.98,\"laser/bin\":95.29,\"laser/cyc_dp\":81.42,\"laser/encl\":6.7,\"laser/pitot\":16.75,\"lase"
    "r/run_in\":133.74},\"7\":{\"fan/fan_in\":204.09,\"laser/bin\":130.09,\"laser/cyc_dp\":111.15,\"l"
    "aser/encl\":9.15,\"laser/pitot\":22.87,\"laser/run_in\":182.39},\"8\":{\"fan/fan_in\":266.5,\"la"
    "ser/bin\":170.32,\"laser/cyc_dp\":145.52,\"laser/encl\":11.98,\"laser/pitot\":29.94,\"laser/ru"
    "n_in\":238.6},\"9\":{\"fan/fan_in\":337.24,\"laser/bin\":215.98,\"laser/cyc_dp\":184.54,\"laser/"
    "encl\":15.19,\"laser/pitot\":37.97,\"laser/run_in\":302.37}},\"C\":{\"0\":{\"fan/fan_in\":0,\"lase"
    "r/encl\":0,\"laser/pitot\":0,\"laser/run_in\":0},\"1\":{\"fan/fan_in\":3.81,\"laser/encl\":0.34,\""
    "laser/pitot\":0.85,\"laser/run_in\":2.74},\"10\":{\"fan/fan_in\":374.16,\"laser/encl\":37.81,\"l"
    "aser/pitot\":94.53,\"laser/run_in\":291.72},\"2\":{\"fan/fan_in\":15.14,\"laser/encl\":1.42,\"la"
    "ser/pitot\":3.54,\"laser/run_in\":11.25},\"3\":{\"fan/fan_in\":33.96,\"laser/encl\":3.26,\"laser"
    "/pitot\":8.15,\"laser/run_in\":25.62},\"4\":{\"fan/fan_in\":60.24,\"laser/encl\":5.87,\"laser/pi"
    "tot\":14.67,\"laser/run_in\":45.88},\"5\":{\"fan/fan_in\":93.99,\"laser/encl\":9.25,\"laser/pito"
    "t\":23.14,\"laser/run_in\":72.06},\"6\":{\"fan/fan_in\":135.19,\"laser/encl\":13.41,\"laser/pito"
    "t\":33.54,\"laser/run_in\":104.16},\"7\":{\"fan/fan_in\":183.86,\"laser/encl\":18.35,\"laser/pit"
    "ot\":45.88,\"laser/run_in\":142.21},\"8\":{\"fan/fan_in\":239.88,\"laser/encl\":24.06,\"laser/pi"
    "tot\":60.16,\"laser/run_in\":186.13},\"9\":{\"fan/fan_in\":303.31,\"laser/encl\":30.55,\"laser/p"
    "itot\":76.37,\"laser/run_in\":235.96}}}"
)

# ======================================================================================
# a minimal `framebuf` so the real driver's text() path works off-target
# ======================================================================================
class _FrameBuffer:
    """Just enough of MicroPython's framebuf.FrameBuffer for st7789.text()."""

    def __init__(self, buf, w, h, fmt=None):
        self.buf, self.w, self.h = buf, w, h

    # MicroPython stores RGB565 little-endian (low byte first). Storing it the other
    # way round here once hid a driver bug that only showed on the real panel.
    def _set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 2
            self.buf[i] = c & 0xFF
            self.buf[i + 1] = (c >> 8) & 0xFF

    def pixel(self, x, y, c=None):
        if c is not None:
            self._set(x, y, c)
            return None
        if not (0 <= x < self.w and 0 <= y < self.h):
            return 0
        i = (y * self.w + x) * 2
        return self.buf[i] | (self.buf[i + 1] << 8)

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
        # Decode exactly as the ST7789 does in 16-bit mode (COLMOD 0x55): each pixel
        # is two bytes, high byte first.
        for i in range(0, len(data) - 1, 2):
            hi, lo = data[i], data[i + 1]
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

    def png_bytes(self, scale=2):
        rows = self.rgb_rows(scale)
        raw = b"".join(b"\x00" + r for r in rows)
        w, h = self.w * scale, self.h * scale

        def chunk(tag, data):
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

        return (b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9))
                + chunk(b"IEND", b""))

    def save_png(self, path, scale=2):
        # Written to a temp file and renamed, because in --live this is rewritten
        # every frame and something (VS Code's preview) is usually reading it.
        path = Path(path)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(self.png_bytes(scale))
        os.replace(tmp, path)
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
        ch=[("cyc_dp", 168.4, True), ("bin", 42.1, True), ("pitot", 61.8, True),
            ("run_in", 96.3, True), ("encl", 18.9, True)]),
    "clog": dict(
        sev="critical", cfm=118, src="taps (pitot suspect)", level=10, mode="auto", rec=10,
        head="Long run restricted - check for a kink",
        ch=[("cyc_dp", 61.2, True), ("bin", 18.7, True), ("pitot", 19.4, True),
            ("run_in", 188.5, True), ("encl", 7.1, True)]),
    "binleak": dict(
        sev="warning", cfm=198, src="pitot", level=7, mode="auto", rec=8,
        head="Dust bin appears to be leaking",
        ch=[("cyc_dp", 151.0, True), ("bin", 6.2, True), ("pitot", 57.1, True),
            ("run_in", 92.8, True), ("encl", 17.4, True)]),
    "pitot": dict(
        sev="warning", cfm=205, src="taps (pitot suspect)", level=7, mode="auto", rec=7,
        head="Pitot disagrees - tip may be blocked",
        ch=[("cyc_dp", 164.9, True), ("bin", 41.0, True), ("pitot", 8.2, True),
            ("run_in", 95.0, True), ("encl", 18.2, True)]),
    "slow": dict(
        sev="advice", cfm=96, src="pitot", level=3, mode="manual", rec=8,
        head="Raise the fan to 8 for brass",
        ch=[("cyc_dp", 39.8, True), ("bin", 11.9, True), ("pitot", 13.0, True),
            ("run_in", 38.4, True), ("encl", 6.6, True)]),
    "sensorfault": dict(
        sev="warning", cfm=203, src="taps", level=7, mode="auto", rec=7,
        head="encl channel not responding",
        ch=[("cyc_dp", 166.1, True), ("bin", 41.6, True), ("pitot", 60.2, True),
            ("run_in", 95.5, True), ("encl", 0.0, False)]),
    "nopc": dict(
        sev="stale", cfm=None, src="no PC link", level=None, mode="", rec=None,
        head="Desktop app not running",
        ch=[("cyc_dp", 167.2, True), ("bin", 41.8, True), ("pitot", 60.9, True),
            ("run_in", 95.9, True), ("encl", 18.5, True)]),
    "fannode": dict(
        sev="ok", cfm=212, src="pitot", level=7, mode="auto", rec=7,
        head="Everything within baseline",
        ch=[("fan_in", 214.6, True)], node="fan"),
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
class LiveNode:
    """A stand-in box: emits telemetry, takes commands, shows what the PC concludes."""

    def channels(self):
        """Channel names this node owns, taken from the profile."""
        pre = self.node_id + "/"
        return [k[len(pre):] for k in _PROFILES[self.profile]["10"] if k.startswith(pre)]

    def __init__(self, node_id, telemetry_port=47810, cmd_port=47811, status_port=47812,
                 period=1.0, ip="192.168.1.42", log=print, profile="A"):
        self.node_id, self.period, self.ip, self.log = node_id, period, ip, log
        self.profile = profile
        self.telemetry_port = telemetry_port
        self.panel = VirtualPanel()
        self.tft = st7789.ST7789(self.panel, self.panel.cs, self.panel.dc, rotation=1)
        self.tft.init()
        self.scr = display_ui.Screen(self.tft, node_id)
        self.scr.splash("simulated node")
        self.scr.layout()

        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.rx = self._bind(status_port)
        self.cmd = self._bind(cmd_port)

        self.level, self.mode, self.rec = 7, "manual", None
        self.sev, self.cfm, self.src = "stale", None, "no PC link"
        self.head = "Waiting for the desktop app"
        self.seq = 0
        self.last_status = 0.0
        self.chans = {}

    @staticmethod
    def _bind(port):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", port))
        s.setblocking(False)
        return s

    def step(self):
        """One frame: publish, drain both inbound sockets, redraw."""
        self.seq += 1
        wobble = math.sin(self.seq / 9.0)
        names = self.channels()
        table = _PROFILES[self.profile][str(self.level)]
        self.chans = {n: {"pa": round(table["%s/%s" % (self.node_id, n)] * (1 + 0.012 * wobble), 2),
                          "t": 24.0, "ok": True}
                      for n in names}
        frame = {"node": self.node_id, "seq": self.seq,
                 "up": self.seq * int(self.period * 1000), "rssi": -61,
                 "ch": self.chans, "env": {"t": 23.9, "rh": 41.0, "p": 94412}}
        if self.node_id == "fan":
            # Same shape as fan.py's telemetry(). driven=False because the real node
            # has FAN_OUTPUT_ENABLED off until the CLOUDLINE UIS pinout is verified:
            # it echoes the last level it was told and cannot see the physical dial,
            # so the app must not let this override the level you set by hand.
            frame["fan"] = {"level": self.level, "mode": "advisory", "driven": False}
        self.tx.sendto(json.dumps(frame).encode(), ("255.255.255.255", self.telemetry_port))

        for m in self._drain(self.cmd):
            c = m.get("cmd")
            if c == "set_level":
                self.level = max(0, min(10, int(m.get("level", self.level))))
                self.log("  <- set_level %d" % self.level)
            elif c:
                self.log("  <- %s" % c)
        for m in self._drain(self.rx):
            if m.get("t") != "status":
                continue
            self.sev = m.get("sev", "ok")
            self.cfm = m.get("cfm")
            self.src = m.get("src", "")
            self.head = m.get("msg", "")
            f = m.get("fan") or {}
            self.mode = f.get("mode", self.mode)
            self.rec = f.get("rec")
            if f.get("level") is not None:
                self.level = f["level"]
            self.last_status = time.time()

        if self.last_status and time.time() - self.last_status > 10:
            self.sev, self.cfm = "stale", None
            self.src, self.head = "no PC link", "Desktop app not running"

        self.scr.status(self.sev, ip=self.ip)
        self.scr.flow(self.cfm, self.src)
        self.scr.fan(self.level, self.mode, self.rec)
        self.scr.headline(self.head, self.sev)
        self.scr.channels([(n, self.chans[n]["pa"], True) for n in names])

    @staticmethod
    def _drain(sock):
        out = []
        while True:
            try:
                data, _ = sock.recvfrom(4096)
                out.append(json.loads(data.decode()))
            except (BlockingIOError, OSError, ValueError):
                return out

    def close(self):
        for s in (self.tx, self.rx, self.cmd):
            try:
                s.close()
            except OSError:
                pass


def run_live(node_id, out_dir, scale, period, telemetry_port, cmd_port, status_port,
             profile="A"):
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / ("screen_live_%s.png" % node_id)
    node = LiveNode(node_id, telemetry_port, cmd_port, status_port, period, profile=profile)
    print("simulated %s node: telemetry -> UDP %d, commands <- %d, status <- %d"
          % (node_id, telemetry_port, cmd_port, status_port))
    print("screen written to %s after every frame. Ctrl+C to stop." % png)
    try:
        while True:
            node.step()
            node.panel.save_png(png, scale)
            time.sleep(period)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        node.close()


# ======================================================================================
# a window, so you can actually watch the thing
# ======================================================================================
def run_window(node_id, live, scenario, scale, period, telemetry_port, cmd_port,
               status_port, profile="A"):
    """Show the panel in a real window (tkinter, stdlib).

    Live: steps the node on a timer. Otherwise: shows a scenario, and Left/Right
    step through them so you can flick between states and compare layouts.
    """
    import tkinter as tk

    root = tk.Tk()
    root.configure(bg="#101418")
    root.resizable(False, False)
    label = tk.Label(root, bd=0, bg="#101418")
    label.pack(padx=10, pady=(10, 4))
    caption = tk.Label(root, bg="#101418", fg="#8a949e",
                       font=("Consolas", 9), anchor="w", justify="left")
    caption.pack(fill="x", padx=12, pady=(0, 8))
    keep = {}

    def show(panel, text):
        img = tk.PhotoImage(data=base64.b64encode(panel.png_bytes(scale)))
        keep["img"] = img                       # PhotoImage is GC'd if not referenced
        label.configure(image=img)
        caption.configure(text=text)

    if live:
        node = LiveNode(node_id, telemetry_port, cmd_port, status_port, period,
                        log=lambda m: caption.configure(text=m.strip()), profile=profile)
        root.title("LumosAir - simulated %s node (live)" % node_id)
        print("simulated %s node: telemetry -> UDP %d, commands <- %d, status <- %d"
              % (node_id, telemetry_port, cmd_port, status_port))

        def tick():
            node.step()
            show(node.panel, "frame %d   level %d   %s   %s"
                             % (node.seq, node.level, node.sev, node.src))
            root.after(int(period * 1000), tick)

        root.protocol("WM_DELETE_WINDOW", lambda: (node.close(), root.destroy()))
        tick()
    else:
        names = sorted(SCENARIOS)
        idx = [names.index(scenario) if scenario in names else 0]

        def draw():
            name = names[idx[0]]
            sc = SCENARIOS[name]
            panel = VirtualPanel()
            paint(panel, sc.get("node", "laser"), sc)
            root.title("LumosAir - box screen: %s" % name)
            show(panel, "%s   (%d of %d)   left/right arrows to change, Esc to close"
                        % (name, idx[0] + 1, len(names)))

        def move(d):
            idx[0] = (idx[0] + d) % len(names)
            draw()

        root.bind("<Left>", lambda e: move(-1))
        root.bind("<Right>", lambda e: move(1))
        root.bind("<Escape>", lambda e: root.destroy())
        draw()

    root.mainloop()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS) + ["all"], default="all")
    ap.add_argument("--node", choices=["laser", "fan"], default="laser")
    ap.add_argument("--live", action="store_true", help="act as a real node on the LAN")
    ap.add_argument("--window", action="store_true",
                    help="show the panel in a window instead of writing PNGs")
    ap.add_argument("--config", choices=["A", "C"], default="A",
                    help="which system layout to emit readings for; match the app")
    ap.add_argument("--scale", type=int, default=2, help="PNG pixel scale")
    ap.add_argument("--period", type=float, default=1.0, help="live: seconds per frame")
    ap.add_argument("--udp", type=int, default=47810)
    ap.add_argument("--cmd-port", type=int, default=47811)
    ap.add_argument("--status-port", type=int, default=47812)
    ap.add_argument("--out", default=str(ROOT / "out"))
    a = ap.parse_args()
    out = Path(a.out)
    if a.window:
        run_window(a.node, a.live, a.scenario if a.scenario != "all" else "healthy",
                   a.scale, a.period, a.udp, a.cmd_port, a.status_port, a.config)
        return 0
    if a.live:
        run_live(a.node, out, a.scale, a.period, a.udp, a.cmd_port, a.status_port, a.config)
        return 0
    run_scenarios(sorted(SCENARIOS) if a.scenario == "all" else [a.scenario], out, a.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

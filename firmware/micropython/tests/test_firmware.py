"""Host-side tests for the node firmware (plain CPython, no hardware).

    python firmware/micropython/tests/test_firmware.py

The drivers take an I2C-like object, so the decoding maths, the mux, the fan
mapping and the telemetry payload can all be checked on a PC before anything is
flashed. Only the pin wiggling is left untested.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT))

from lumosair import sensors as S          # noqa: E402
from lumosair.fan import FanOutput         # noqa: E402
from lumosair.node import Channel          # noqa: E402
from lumosair import st7789                # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS ", name)
    else:
        failed += 1
        print("  FAIL ", name, detail)


def near(a, b, tol):
    return a is not None and abs(a - b) <= tol


# ---------------------------------------------------------------- fakes
class FakeI2C:
    """Records writes; returns queued frames."""

    def __init__(self, frames=None, mem=None):
        self.frames = list(frames or [])
        self.mem = dict(mem or {})
        self.writes = []

    def writeto(self, addr, data):
        self.writes.append((addr, bytes(data)))

    def readfrom(self, addr, n):
        if not self.frames:
            raise OSError("no data")
        return self.frames.pop(0)[:n]

    def writeto_mem(self, addr, reg, data):
        self.writes.append((addr, reg, bytes(data)))
        if reg == 0x30:
            self.mem[0x30] = bytes([0x00])       # conversion finishes immediately

    def readfrom_mem(self, addr, reg, n):
        return self.mem.get(reg, bytes(n))[:n]


class FakeSPI:
    def __init__(self):
        self.bytes_written = 0
        self.commands = []

    def write(self, data):
        self.bytes_written += len(data)


class FakePin:
    def __init__(self, value=0):
        self._v = value

    def value(self, v=None):
        if v is None:
            return self._v
        self._v = v


def sdp_frame(dp, temp_raw, scale):
    def word(v):
        b = v.to_bytes(2, "big", signed=v < 0)
        return b + bytes([S.crc8(b)])
    return word(dp) + word(temp_raw) + word(scale)


# ---------------------------------------------------------------- tests
print("Sensor drivers")
check("Sensirion CRC-8 of 0xBEEF is 0x92", S.crc8(b"\xbe\xef") == 0x92, hex(S.crc8(b"\xbe\xef")))

i2c = FakeI2C([sdp_frame(1200, 4800, 60)])
sdp = S.SDP8xx(i2c)
pa, t = sdp.read()
check("SDP810 scales pressure by the reported factor", near(pa, 20.0, 1e-9), pa)
check("SDP810 temperature is raw/200", near(t, 24.0, 1e-9), t)

i2c = FakeI2C([sdp_frame(-300, 4000, 60)])
pa, _ = S.SDP8xx(i2c).read()
check("SDP810 handles negative pressure", near(pa, -5.0, 1e-9), pa)

bad = bytearray(sdp_frame(1200, 4800, 60))
bad[2] ^= 0xFF
try:
    S.SDP8xx(FakeI2C([bytes(bad)])).read()
    check("SDP810 rejects a bad CRC", False)
except ValueError:
    check("SDP810 rejects a bad CRC", True)

i2c = FakeI2C()
S.SDP8xx(i2c).start()
check("SDP810 start sends stop then 0x3615",
      i2c.writes[-1][1] == b"\x36\x15" and i2c.writes[0][1] == b"\x3f\xf9", i2c.writes)

# XGZP: 24-bit signed / K, temperature /256
raw = (4096).to_bytes(3, "big") + (25 * 256).to_bytes(2, "big")
x = S.XGZP6897D(FakeI2C(mem={0x30: bytes([0]), 0x06: raw}), k=4096)
pa, t = x.read()
check("XGZP6897D divides by K", near(pa, 1.0, 1e-9), pa)
check("XGZP6897D temperature is raw/256", near(t, 25.0, 1e-9), t)

neg = (0x1000000 - 8192).to_bytes(3, "big") + (0).to_bytes(2, "big")
x = S.XGZP6897D(FakeI2C(mem={0x30: bytes([0]), 0x06: neg}), k=4096)
pa, _ = x.read()
check("XGZP6897D sign-extends", near(pa, -2.0, 1e-9), pa)

print("Multiplexer")
i2c = FakeI2C()
mux = S.Mux(i2c, 0x70)
mux.select(3)
check("mux writes 1 << port", i2c.writes[-1] == (0x70, bytes([0x08])), i2c.writes[-1])
n = len(i2c.writes)
mux.select(3)
check("mux caches the selected port", len(i2c.writes) == n)
mux.invalidate()
mux.select(3)
check("invalidate forces a re-select", len(i2c.writes) == n + 1)
check("addr 0 means no multiplexer", S.Mux(FakeI2C(), 0).select(5) is True)

print("Channel")
ch = Channel({"name": "pitot", "mux": 2, "type": "sdp810", "sign": 1},
             FakeI2C([sdp_frame(1200, 4800, 60)] * 4), S.Mux(FakeI2C(), 0))
ch.ready = True
ch.offset = 2.0
ch.sample()
ch.sample()
got = ch.drain()
check("channel averages and applies the zero offset", near(got[0], 18.0, 1e-6), got)
check("channel drain is empty afterwards", ch.drain() is None)

ch = Channel({"name": "encl", "mux": 0, "type": "sdp810", "sign": -1},
             FakeI2C([sdp_frame(1200, 4800, 60)]), S.Mux(FakeI2C(), 0))
ch.ready = True
ch.sample()
check("sign flips the reading", near(ch.drain()[0], -20.0, 1e-6))

zeroing = {}
ch = Channel({"name": "bin", "mux": 0, "type": "sdp810"},
             FakeI2C([sdp_frame(60, 4800, 60)]), S.Mux(FakeI2C(), 0))
ch.ready = True
ch.sample(zeroing)
check("zeroing collects pre-offset samples", zeroing["bin"] == [1.0], zeroing)


class Cfg:
    FAN_LEVELS = 10
    FAN_DUTY_MIN = 0.10
    FAN_DUTY_MAX = 1.00
    FAN_DEFAULT_LEVEL = 10
    FAN_OUTPUT_ENABLED = False
    FAN_OUTPUT_KIND = "pwm"
    FAN_OUTPUT_PIN = 25
    FAN_PWM_FREQ = 1000


print("Fan output")
fan = FanOutput(Cfg, log=lambda *a: None)
check("level 1 maps to the minimum duty", near(fan.duty_for(1), 0.10, 1e-9), fan.duty_for(1))
check("level 10 maps to full duty", near(fan.duty_for(10), 1.00, 1e-9), fan.duty_for(10))
check("level 0 is off", fan.duty_for(0) == 0.0)
check("duty rises monotonically",
      all(fan.duty_for(i) < fan.duty_for(i + 1) for i in range(1, 10)))
fan.apply(7)
check("apply clamps and records the level", fan.level == 7)
fan.apply(99)
check("apply clamps above the maximum", fan.level == 10)
check("output stays advisory until enabled in config", fan.telemetry()["driven"] is False)

print("Telemetry payload")
sys.modules.setdefault("config", type("c", (), {})())
payload = {"node": "laser", "seq": 1, "up": 100,
           "ch": {"pitot": {"pa": 46.8, "t": 24.0, "ok": True},
                  "bin": {"ok": False}},
           "env": {"t": 23.9, "rh": 41.0, "p": 94412},
           "fan": {"level": 7, "mode": "auto", "driven": False}}
text = json.dumps(payload)
check("payload is compact enough for one datagram", len(text) < 512, len(text))
back = json.loads(text)
check("payload keeps the fields the PC app parses",
      back["node"] == "laser" and back["ch"]["pitot"]["pa"] == 46.8
      and back["ch"]["bin"]["ok"] is False and back["env"]["p"] == 94412
      and back["fan"]["level"] == 7)

print("Display driver")
spi = FakeSPI()
tft = st7789.ST7789(spi, FakePin(1), FakePin(), rotation=1)
check("rotation 1 gives a 320x240 screen", (tft.width, tft.height) == (320, 240))
before = spi.bytes_written
tft.fill_rect(0, 0, 320, 20, st7789.BLUE)
check("fill_rect pushes 2 bytes per pixel",
      spi.bytes_written - before >= 320 * 20 * 2, spi.bytes_written - before)
before = spi.bytes_written
end_x = tft.seg7("142", 10, 40)
check("seg7 draws three digits and advances x", end_x == 10 + 3 * (34 + 10), end_x)
check("seg7 writes pixels", spi.bytes_written > before)
check("colour helper packs RGB565 byte-swapped", st7789.rgb(255, 0, 0) == 0x00F8,
      hex(st7789.rgb(255, 0, 0)))


def lit_segments(ch, digit_w=34, digit_h=58, thick=7):
    """Which of the seven bars seg7 actually paints for one character.

    Records fill_rect calls in the digit's colour and maps each back to its slot
    in _SEGMENTS. Checking the count alone would not have caught reading the
    bitmap backwards, because a mirrored digit lights the same NUMBER of bars.
    """
    t = st7789.ST7789(FakeSPI(), FakePin(1), FakePin(), rotation=1)
    calls = []
    t.fill_rect = lambda x, y, w, h, c: calls.append((x, y, w, h, c))
    t.seg7(ch, 0, 0, digit_w=digit_w, digit_h=digit_h, thick=thick,
           color=st7789.WHITE, bg=st7789.DARK)
    half = (digit_h - thick) / 2.0
    want = {}
    for i, (sx, sy, horiz) in enumerate(st7789._SEGMENTS):
        want[(int(sx * (digit_w - thick)), int(sy * half), horiz)] = i
    out = set()
    for x, y, w, h, c in calls:
        if c != st7789.WHITE:
            continue
        out.add(want.get((x, y, w == digit_w)))
    return out - {None}


# segment indices: 0 top, 1 top-left, 2 top-right, 3 middle,
#                  4 bottom-left, 5 bottom-right, 6 bottom
check("seg7 '1' lights only the two right-hand bars", lit_segments("1") == {2, 5},
      lit_segments("1"))
check("seg7 '7' lights top + both right bars", lit_segments("7") == {0, 2, 5},
      lit_segments("7"))
check("seg7 '4' has no top bar and no bottom bar", lit_segments("4") == {1, 2, 3, 5},
      lit_segments("4"))
check("seg7 '6' has a bottom-left bar but no top-right", lit_segments("6") == {0, 1, 3, 4, 5, 6},
      lit_segments("6"))
check("seg7 '9' has a top-right bar but no bottom-left", lit_segments("9") == {0, 1, 2, 3, 5, 6},
      lit_segments("9"))
check("seg7 '3' is not a mirrored 'E'", lit_segments("3") == {0, 2, 3, 5, 6},
      lit_segments("3"))
check("seg7 '8' lights all seven", lit_segments("8") == {0, 1, 2, 3, 4, 5, 6},
      lit_segments("8"))
check("seg7 '-' is the middle bar alone", lit_segments("-") == {3}, lit_segments("-"))

# ---------------------------------------------------------------- screen redraws
# These use the node simulator's virtual panel, which decodes the driver's real SPI
# command stream into a framebuffer, so they check what the glass would show.
print("Screen redraws")
sys.path.insert(0, str(ROOT / "tools"))
import simulate_node as SIM                          # noqa: E402


def screen_after(steps, node="fan"):
    """Framebuffer after applying a list of (method, args) to a fresh Screen."""
    panel = SIM.VirtualPanel()
    tft = SIM.st7789.ST7789(panel, panel.cs, panel.dc, rotation=1)
    tft.init()
    scr = SIM.display_ui.Screen(tft, node)
    scr.layout()
    for name, args in steps:
        getattr(scr, name)(*args)
    return bytes(panel.fb)


# A value that needs fewer digits than the one before it must not leave the old
# ones on screen: going from fan level 10 to 7 used to display "70".
shrunk = screen_after([("fan", (10, "auto", None)), ("fan", (7, "auto", None))])
clean = screen_after([("fan", (7, "auto", None))])
check("fan 10 -> 7 leaves no stale digit", shrunk == clean,
      "%d bytes differ" % sum(1 for a, b in zip(shrunk, clean) if a != b))

shrunk = screen_after([("fan", (10, "auto", None)), ("fan", (None, "", None))])
clean = screen_after([("fan", (None, "", None))])
check("fan 10 -> no level leaves no stale digit", shrunk == clean,
      "%d bytes differ" % sum(1 for a, b in zip(shrunk, clean) if a != b))

shrunk = screen_after([("flow", (212, "pitot")), ("flow", (96, "pitot"))], node="laser")
clean = screen_after([("flow", (96, "pitot"))], node="laser")
check("flow 212 -> 96 leaves no stale digit", shrunk == clean,
      "%d bytes differ" % sum(1 for a, b in zip(shrunk, clean) if a != b))

shrunk = screen_after([("flow", (212, "pitot")), ("flow", (None, "no PC link"))], node="laser")
clean = screen_after([("flow", (None, "no PC link"))], node="laser")
check("flow 212 -> --- leaves no stale digit", shrunk == clean,
      "%d bytes differ" % sum(1 for a, b in zip(shrunk, clean) if a != b))


# Fills and text must reach the panel in the same byte order. They didn't: fill_rect
# wrote high byte first, framebuf writes low byte first, so on the real ST7789 the
# dark background came out pink and the status band stopped where the text did.
def panel_rgb(panel, x, y):
    j = (y * panel.w + x) * 2
    v = (panel.fb[j] << 8) | panel.fb[j + 1]
    return ((v >> 11) & 0x1F) * 255 // 31, ((v >> 5) & 0x3F) * 255 // 63, (v & 0x1F) * 255 // 31


panel = SIM.VirtualPanel()
tft = SIM.st7789.ST7789(panel, panel.cs, panel.dc, rotation=1)
tft.init()
tft.fill_rect(0, 0, 40, 40, SIM.st7789.RED)
tft.text(" ", 100, 0, SIM.st7789.WHITE, SIM.st7789.RED, 2)
fill_px, text_px = panel_rgb(panel, 5, 5), panel_rgb(panel, 104, 4)
check("fill_rect and text background give the same colour", fill_px == text_px,
      (fill_px, text_px))
check("red decodes as red on the panel", fill_px[0] > 200 and fill_px[1] < 100 and fill_px[2] < 100,
      fill_px)
tft.fill_rect(0, 0, 40, 40, SIM.st7789.DARK)
check("the dark background decodes as near-black, not pink", max(panel_rgb(panel, 5, 5)) < 40,
      panel_rgb(panel, 5, 5))

# ---------------------------------------------------------------- bench mode
print("Bench mode")
from lumosair import benchsim                # noqa: E402

check("bench table matches the simulator's profiles",
      all(benchsim.PROFILES[o][lvl][k.split("/", 1)[1]] == v
          for o, levels in SIM._PROFILES.items() for lvl in range(11)
          for k, v in levels[str(lvl)].items()))

level = [7]
bench = Channel({"name": "cyc_dp", "mux": 0, "type": "sdp810"}, None, benchsim.NoMux())
bench.driver = benchsim.Driver("cyc_dp", "A", lambda: level[0])
check("bench channel starts", bench.start())
for _ in range(5):
    bench.sample()
pa, _t = bench.drain()
check("bench reads the model's value at level 7 (111.15 Pa, within the wobble)",
      abs(pa - 111.15) <= 111.15 * 0.013, pa)
level[0] = 3
bench.sample()
check("bench follows the fan level", abs(bench.drain()[0] - 20.03) <= 20.03 * 0.013)

no_cyclone = Channel({"name": "cyc_dp", "mux": 0, "type": "sdp810"}, None, benchsim.NoMux())
no_cyclone.driver = benchsim.Driver("cyc_dp", "C", lambda: 7)
check("Option C has no cyclone, so its channel is not found", not no_cyclone.start())

print()
print(f"{passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)

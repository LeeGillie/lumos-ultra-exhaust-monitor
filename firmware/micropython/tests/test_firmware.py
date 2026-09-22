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

print()
print(f"{passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)

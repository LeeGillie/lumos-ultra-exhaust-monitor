"""Small ST7789 driver for the 2.0" 240x320 IPS module (4-wire SPI).

The ESP32 doesn't have room for a full 240x320 RGB565 framebuffer (150 KB), so
this driver keeps one reusable stripe buffer and paints regions: solid fills,
8x8 text (optionally scaled) and a seven-segment renderer for the big readouts.

Wiring (module pulls RES and BLK high itself, so those pins are optional):
    SCL -> SPI SCK      SDA -> SPI MOSI     DC -> any GPIO
    CS  -> any GPIO     VCC -> 3V3          GND -> GND
"""

try:
    import framebuf
    from machine import Pin
    from time import sleep_ms
except ImportError:                                  # host tests
    framebuf = None
    Pin = None

    def sleep_ms(ms):
        import time
        time.sleep(ms / 1000)


def rgb(r, g, b):
    """8-8-8 to RGB565, byte-swapped for the panel."""
    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((v & 0xFF) << 8) | (v >> 8)


BLACK = rgb(0, 0, 0)
WHITE = rgb(235, 238, 240)
GREY = rgb(120, 130, 140)
DARK = rgb(20, 24, 30)
PANEL = rgb(32, 38, 46)
GREEN = rgb(63, 185, 80)
BLUE = rgb(79, 163, 224)
AMBER = rgb(216, 180, 58)
ORANGE = rgb(232, 128, 46)
RED = rgb(224, 74, 74)

# Seven-segment layout: (x, y, horizontal?) in a 1.0 x 2.0 cell
_SEGMENTS = (
    (0.0, 0.0, True), (0.0, 0.0, False), (1.0, 0.0, False),
    (0.0, 1.0, True), (0.0, 1.0, False), (1.0, 1.0, False), (0.0, 2.0, True),
)
_DIGITS = {
    "0": 0b1110111, "1": 0b0100100, "2": 0b1011101, "3": 0b1101101, "4": 0b0101110,
    "5": 0b1101011, "6": 0b1111011, "7": 0b0100101, "8": 0b1111111, "9": 0b1101111,
    "-": 0b0001000, " ": 0b0000000,
}


class ST7789:
    def __init__(self, spi, cs, dc, rst=None, bl=None, width=240, height=320, rotation=0):
        self.spi, self.cs, self.dc, self.rst, self.bl = spi, cs, dc, rst, bl
        self.rotation = rotation
        self.width, self.height = (width, height) if rotation in (0, 2) else (height, width)
        self._buf = bytearray(240 * 24 * 2)          # reusable stripe, ~11.5 KB

    # ---------------- low level ----------------
    def _cmd(self, c, data=None):
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc.value(1)
            self.spi.write(data)
        self.cs.value(1)

    def init(self):
        if self.rst:
            self.rst.value(0); sleep_ms(20); self.rst.value(1); sleep_ms(120)
        self._cmd(0x01); sleep_ms(150)               # software reset
        self._cmd(0x11); sleep_ms(120)               # sleep out
        self._cmd(0x3A, b"\x55")                     # 16-bit colour
        madctl = {0: 0x00, 1: 0x60, 2: 0xC0, 3: 0xA0}[self.rotation]
        self._cmd(0x36, bytes([madctl]))
        self._cmd(0x21)                              # inversion on (IPS panels)
        self._cmd(0x13)
        self._cmd(0x29); sleep_ms(20)                # display on
        if self.bl:
            self.bl.value(1)
        self.fill(BLACK)

    def _window(self, x, y, w, h):
        x0, x1, y0, y1 = x, x + w - 1, y, y + h - 1
        self._cmd(0x2A, bytes([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._cmd(0x2B, bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
        self._cmd(0x2C)

    def blit(self, buf, x, y, w, h):
        self._window(x, y, w, h)
        self.cs.value(0)
        self.dc.value(1)
        self.spi.write(buf)
        self.cs.value(1)

    # ---------------- drawing ----------------
    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        rows = max(1, min(h, len(self._buf) // (2 * w)))
        chunk = memoryview(self._buf)[:w * rows * 2]
        hi, lo = color >> 8, color & 0xFF
        for i in range(0, len(chunk), 2):
            chunk[i] = hi
            chunk[i + 1] = lo
        done = 0
        while done < h:
            n = min(rows, h - done)
            self.blit(memoryview(chunk)[:w * n * 2], x, y + done, w, n)
            done += n

    def fill(self, color):
        self.fill_rect(0, 0, self.width, self.height, color)

    def text(self, s, x, y, fg=WHITE, bg=DARK, scale=1):
        """8x8 font, optionally scaled. Paints its own background (no flicker)."""
        if framebuf is None:
            return
        w, h = 8 * len(s) * scale, 8 * scale
        if w * h * 2 > len(self._buf):
            s = s[:len(self._buf) // (2 * 64 * scale * scale)]
            w = 8 * len(s) * scale
        mv = memoryview(self._buf)[:w * h * 2]
        fb = framebuf.FrameBuffer(mv, w, h, framebuf.RGB565)
        fb.fill(bg)
        if scale == 1:
            fb.text(s, 0, 0, fg)
        else:
            small = framebuf.FrameBuffer(bytearray(8 * len(s) * 8 * 2), 8 * len(s), 8, framebuf.RGB565)
            small.fill(bg)
            small.text(s, 0, 0, fg)
            for yy in range(8):
                for xx in range(8 * len(s)):
                    if small.pixel(xx, yy) == fg:
                        fb.fill_rect(xx * scale, yy * scale, scale, scale, fg)
        self.blit(mv, x, y, w, h)
        return w

    def seg7(self, s, x, y, digit_w=34, digit_h=58, thick=7, color=WHITE, bg=DARK, gap=10):
        """Seven-segment number, e.g. '142'. Much cheaper than a scaled font."""
        self.fill_rect(x, y, (digit_w + gap) * len(s), digit_h, bg)
        for ch in s:
            mask = _DIGITS.get(ch)
            if ch == ".":
                self.fill_rect(x + 2, y + digit_h - thick, thick, thick, color)
                x += thick + 6
                continue
            if mask is None:
                x += digit_w + gap
                continue
            half = (digit_h - thick) / 2.0
            for i, (sx, sy, horiz) in enumerate(_SEGMENTS):
                # _DIGITS is written LSB-first: bit i is _SEGMENTS[i].
                if not (mask >> i) & 1:
                    continue
                px = int(x + sx * (digit_w - thick))
                py = int(y + sy * half)
                if horiz:
                    self.fill_rect(px, py, digit_w, thick, color)
                else:
                    self.fill_rect(px, py, thick, int(half) + thick, color)
            x += digit_w + gap
        return x

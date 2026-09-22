"""Pressure-sensor drivers: Sensirion SDP8xx, CFSensor XGZP6897D, TCA9548A mux.

Pure MicroPython, but every class takes an I2C-like object, so the drivers are
testable on a PC with a fake bus (see firmware/micropython/tests/).
"""

try:
    from time import sleep_ms, ticks_ms, ticks_diff
except ImportError:  # CPython, for the tests
    import time as _t

    def sleep_ms(ms): _t.sleep(ms / 1000)
    def ticks_ms(): return int(_t.monotonic() * 1000)
    def ticks_diff(a, b): return a - b


class Mux:
    """TCA9548A I2C multiplexer. addr=0 means 'no multiplexer fitted'."""

    def __init__(self, i2c, addr=0x70):
        self.i2c = i2c
        self.addr = addr
        self._current = None

    def select(self, port):
        if not self.addr:
            return True
        if port == self._current:
            return True
        try:
            self.i2c.writeto(self.addr, bytes([1 << port]))
            self._current = port
            return True
        except OSError:
            self._current = None
            return False

    def invalidate(self):
        self._current = None


def crc8(data):
    """Sensirion CRC-8: polynomial 0x31, init 0xFF."""
    crc = 0xFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


class SDP8xx:
    """SDP810 / SDP811 differential-pressure sensor (I2C 0x25).

    Continuous mode, temperature-compensated differential pressure, averaged
    until read (command 0x3615). Each read returns pressure, temperature and the
    scale factor, each followed by a CRC byte.
    """

    ADDR = 0x25
    CMD_START = b"\x36\x15"
    CMD_STOP = b"\x3f\xf9"

    def __init__(self, i2c, addr=ADDR):
        self.i2c = i2c
        self.addr = addr

    def start(self):
        try:
            self.i2c.writeto(self.addr, self.CMD_STOP)
            sleep_ms(2)
        except OSError:
            pass                       # NACKs when idle, which is fine
        self.i2c.writeto(self.addr, self.CMD_START)
        sleep_ms(25)                   # first conversion
        return True

    def read(self):
        """Returns (pascals, temperature_C). Raises OSError/ValueError on failure."""
        raw = self.i2c.readfrom(self.addr, 9)
        if len(raw) != 9:
            raise OSError("short read")
        for i in range(0, 9, 3):
            if crc8(raw[i:i + 2]) != raw[i + 2]:
                raise ValueError("crc")
        dp = int.from_bytes(raw[0:2], "big")
        t = int.from_bytes(raw[3:5], "big")
        scale = int.from_bytes(raw[6:8], "big")
        if dp >= 0x8000:
            dp -= 0x10000
        if t >= 0x8000:
            t -= 0x10000
        if scale == 0:
            raise ValueError("scale 0")
        return dp / scale, t / 200.0


class XGZP6897D:
    """CFSensor XGZP6897D (I2C 0x6D).

    K comes from the datasheet's range table: below 1 kPa use 8192, a ±1 kPa
    part uses 4096. Register 0x30 starts a combined pressure+temperature
    conversion; bit 3 clears when the result is ready.
    """

    ADDR = 0x6D

    def __init__(self, i2c, k=4096, addr=ADDR):
        self.i2c = i2c
        self.k = k
        self.addr = addr

    def start(self):
        self.i2c.writeto_mem(self.addr, 0x30, b"\x0a")
        return True

    def read(self):
        self.i2c.writeto_mem(self.addr, 0x30, b"\x0a")
        t0 = ticks_ms()
        while ticks_diff(ticks_ms(), t0) < 40:
            if not (self.i2c.readfrom_mem(self.addr, 0x30, 1)[0] & 0x08):
                break
            sleep_ms(2)
        else:
            raise OSError("conversion timeout")
        raw = self.i2c.readfrom_mem(self.addr, 0x06, 5)
        p = (raw[0] << 16) | (raw[1] << 8) | raw[2]
        if p & 0x800000:
            p -= 0x1000000
        t = (raw[3] << 8) | raw[4]
        if t & 0x8000:
            t -= 0x10000
        return p / self.k, t / 256.0


class BME280:
    """Minimal BME280 (temperature, pressure, humidity) — used for air density."""

    def __init__(self, i2c, addr=0x76):
        self.i2c = i2c
        self.addr = addr
        self._cal = None

    def start(self):
        c1 = self.i2c.readfrom_mem(self.addr, 0x88, 26)
        c2 = self.i2c.readfrom_mem(self.addr, 0xE1, 7)
        u16 = lambda b, i: b[i] | (b[i + 1] << 8)
        s16 = lambda b, i: u16(b, i) - 65536 if u16(b, i) > 32767 else u16(b, i)
        self._cal = dict(
            T1=u16(c1, 0), T2=s16(c1, 2), T3=s16(c1, 4),
            P1=u16(c1, 6), P2=s16(c1, 8), P3=s16(c1, 10), P4=s16(c1, 12),
            P5=s16(c1, 14), P6=s16(c1, 16), P7=s16(c1, 18), P8=s16(c1, 20), P9=s16(c1, 22),
            H1=c1[25], H2=(c2[1] << 8 | c2[0]) - 65536 if (c2[1] << 8 | c2[0]) > 32767 else (c2[1] << 8 | c2[0]),
            H3=c2[2],
            H4=(c2[3] << 4) | (c2[4] & 0x0F),
            H5=(c2[5] << 4) | (c2[4] >> 4),
            H6=c2[6] - 256 if c2[6] > 127 else c2[6])
        self.i2c.writeto_mem(self.addr, 0xF2, b"\x01")      # humidity oversampling x1
        self.i2c.writeto_mem(self.addr, 0xF4, b"\x27")      # temp/press x1, normal mode
        self.i2c.writeto_mem(self.addr, 0xF5, b"\xa0")      # standby 1 s
        return True

    def read(self):
        """Returns (temperature_C, relative_humidity_pct, pressure_Pa)."""
        c = self._cal
        d = self.i2c.readfrom_mem(self.addr, 0xF7, 8)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        adc_h = (d[6] << 8) | d[7]

        v1 = (adc_t / 16384.0 - c["T1"] / 1024.0) * c["T2"]
        v2 = ((adc_t / 131072.0 - c["T1"] / 8192.0) ** 2) * c["T3"]
        t_fine = v1 + v2
        temp = t_fine / 5120.0

        v1 = t_fine / 2.0 - 64000.0
        v2 = v1 * v1 * c["P6"] / 32768.0 + v1 * c["P5"] * 2.0
        v2 = v2 / 4.0 + c["P4"] * 65536.0
        v1 = (c["P3"] * v1 * v1 / 524288.0 + c["P2"] * v1) / 524288.0
        v1 = (1.0 + v1 / 32768.0) * c["P1"]
        if v1 == 0:
            return temp, 0.0, 0.0
        p = 1048576.0 - adc_p
        p = (p - v2 / 4096.0) * 6250.0 / v1
        v1 = c["P9"] * p * p / 2147483648.0
        v2 = p * c["P8"] / 32768.0
        press = p + (v1 + v2 + c["P7"]) / 16.0

        h = t_fine - 76800.0
        h = ((adc_h - (c["H4"] * 64.0 + c["H5"] / 16384.0 * h)) *
             (c["H2"] / 65536.0 * (1.0 + c["H6"] / 67108864.0 * h *
                                   (1.0 + c["H3"] / 67108864.0 * h))))
        h = h * (1.0 - c["H1"] * h / 524288.0)
        hum = min(100.0, max(0.0, h))
        return temp, hum, press

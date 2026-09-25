"""The node: sample sensors, publish telemetry, drive the display, obey commands."""

import json

from . import sensors as S
from .fan import FanOutput
from .net import Link, connect_wifi

try:
    from machine import I2C, Pin, SPI, WDT, reset
    from time import sleep_ms, ticks_ms, ticks_diff
except ImportError:                                   # host tests
    I2C = Pin = SPI = WDT = None

    def reset(): raise SystemExit

    import time as _t

    def sleep_ms(ms): _t.sleep(ms / 1000)
    def ticks_ms(): return int(_t.monotonic() * 1000)
    def ticks_diff(a, b): return a - b

OFFSETS_FILE = "offsets.json"


class Channel:
    def __init__(self, spec, i2c, mux):
        self.name = spec["name"]
        self.port = spec.get("mux", 0)
        self.sign = spec.get("sign", 1)
        self.kind = spec.get("type", "sdp810")
        self.mux = mux
        self.driver = (S.SDP8xx(i2c) if self.kind == "sdp810"
                       else S.XGZP6897D(i2c, spec.get("k", 4096)))
        self.ready = False
        self.ok = False
        self.offset = 0.0
        self.sum = 0.0
        self.sum_t = 0.0
        self.count = 0
        self.last_pa = None
        self.errors = 0
        self.last_try = 0

    def start(self):
        self.last_try = ticks_ms()
        try:
            self.ready = bool(self.mux.select(self.port) and self.driver.start())
        except Exception:                             # noqa: BLE001
            self.ready = False
        return self.ready

    def sample(self, zeroing=None):
        if not self.ready:
            if ticks_diff(ticks_ms(), self.last_try) > 5000:
                self.start()
            if not self.ready:
                self.ok = False
                return
        try:
            if not self.mux.select(self.port):
                raise OSError("mux")
            pa, t = self.driver.read()
        except Exception:                             # noqa: BLE001
            self.errors += 1
            if self.errors >= 10:
                self.ready = self.ok = False
                self.errors = 0
                self.mux.invalidate()
            return
        self.errors = 0
        self.ok = True
        pa *= self.sign
        if zeroing is not None:
            zeroing.setdefault(self.name, []).append(pa)
        pa -= self.offset
        self.sum += pa
        self.sum_t += t
        self.count += 1

    def drain(self):
        """Average since the last call, or None when nothing was read."""
        if not self.count:
            return None
        pa = self.sum / self.count
        t = self.sum_t / self.count
        self.sum = self.sum_t = 0.0
        self.count = 0
        self.last_pa = pa
        return pa, t


class Node:
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.seq = 0
        self.zeroing = None
        self.zero_start = 0
        self.screen = None
        self.wlan = None
        self.env = None
        self._last_env = 0
        self._last_pub = 0
        self._last_draw = 0

        self.i2c = I2C(0, scl=Pin(cfg.I2C_SCL), sda=Pin(cfg.I2C_SDA), freq=cfg.I2C_HZ)
        self.mux = S.Mux(self.i2c, cfg.TCA9548A_ADDR)
        self.channels = [Channel(spec, self.i2c, self.mux) for spec in cfg.CHANNELS]
        self.bme = S.BME280(self.i2c, cfg.BME280_ADDR) if cfg.HAS_BME280 else None
        self.fan = FanOutput(cfg, log)
        self.led = Pin(cfg.STATUS_LED, Pin.OUT) if cfg.STATUS_LED is not None else None

        # Bench mode: no sensors wired, so report what the model predicts at the fan
        # level the app last broadcast. Everything downstream of the sensors is real.
        self.bench_level = 7
        if getattr(cfg, "BENCH_SIMULATE", False):
            from . import benchsim
            profile = getattr(cfg, "BENCH_PROFILE", "A")
            for ch in self.channels:
                ch.mux = benchsim.NoMux()
                ch.driver = benchsim.Driver(ch.name, profile, lambda: self.bench_level)
            self.log("BENCH MODE: simulated sensor readings, profile %s" % profile)

        self._load_offsets()
        for ch in self.channels:
            self.log("channel %-8s %s" % (ch.name, "ok" if ch.start() else "NOT FOUND"))
        if self.bme:
            try:
                self.bme.start()
            except Exception as e:                    # noqa: BLE001
                self.log("bme280:", e)
                self.bme = None

    # ---------------- display ----------------
    def start_display(self):
        cfg = self.cfg
        if not cfg.HAS_DISPLAY:
            return
        from .display_ui import Screen
        from .st7789 import ST7789
        spi = SPI(cfg.DISPLAY_SPI, baudrate=cfg.DISPLAY_BAUD, polarity=1, phase=1,
                  sck=Pin(cfg.DISPLAY_SCK), mosi=Pin(cfg.DISPLAY_MOSI))
        tft = ST7789(spi, Pin(cfg.DISPLAY_CS, Pin.OUT, value=1), Pin(cfg.DISPLAY_DC, Pin.OUT),
                     rst=Pin(cfg.DISPLAY_RST, Pin.OUT) if cfg.DISPLAY_RST is not None else None,
                     bl=Pin(cfg.DISPLAY_BL, Pin.OUT) if cfg.DISPLAY_BL is not None else None,
                     rotation=cfg.DISPLAY_ROTATION)
        tft.init()
        self.screen = Screen(tft, cfg.NODE_ID)
        self.screen.splash("starting...")

    # ---------------- zero offsets ----------------
    def _load_offsets(self):
        try:
            with open(OFFSETS_FILE) as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return
        for ch in self.channels:
            ch.offset = float(saved.get(ch.name, 0.0))

    def _save_offsets(self):
        try:
            with open(OFFSETS_FILE, "w") as f:
                json.dump({c.name: c.offset for c in self.channels}, f)
        except OSError as e:
            self.log("offsets not saved:", e)

    def start_zero(self):
        self.zeroing = {}
        self.zero_start = ticks_ms()
        self.log("zeroing: keep the fan off for 3 s")

    def finish_zero(self):
        samples, self.zeroing = self.zeroing, None
        for ch in self.channels:
            vals = samples.get(ch.name, [])
            if len(vals) < 10:
                continue
            off = sum(vals) / len(vals)
            if abs(off) > 20:                         # that is airflow, not an offset
                self.log("%s: %.2f Pa looks like airflow, skipped" % (ch.name, off))
                continue
            ch.offset = off
            self.log("%s offset %.3f Pa" % (ch.name, off))
        self._save_offsets()

    # ---------------- commands ----------------
    def handle(self, msg):
        cmd = msg.get("cmd", "")
        self.log("command:", cmd)
        if cmd == "zero":
            self.start_zero()
        elif cmd == "clear_zero":
            for ch in self.channels:
                ch.offset = 0.0
            self._save_offsets()
        elif cmd == "set_level":
            level = int(msg.get("level", self.fan.level))
            self.fan.mode = msg.get("mode", self.fan.mode)
            driven = self.fan.apply(level)
            self.log("fan level %d (%s)" % (level, "driven" if driven else "advisory only"))
        elif cmd == "info":
            self.link.publish(self.info())
        elif cmd == "update":
            self.do_update(msg.get("url") or self.cfg.OTA_URL)
        elif cmd == "reboot":
            sleep_ms(100)
            reset()

    def do_update(self, url):
        from . import ota
        if self.screen:
            self.screen.splash("updating...")
        try:
            if ota.update(url, self.log):
                sleep_ms(300)
                reset()
        except Exception as e:                        # noqa: BLE001
            self.log("ota failed:", e)
            if self.screen:
                self.screen.splash("update failed")
                sleep_ms(1500)
                self.screen.layout()

    # ---------------- payloads ----------------
    def telemetry(self):
        self.seq += 1
        ch = {}
        for c in self.channels:
            got = c.drain()
            if got is None:
                ch[c.name] = {"ok": False}
            else:
                pa, t = got
                ch[c.name] = {"pa": round(pa, 2), "t": round(t, 1), "ok": True}
        msg = {"node": self.cfg.NODE_ID, "seq": self.seq, "up": ticks_ms(), "ch": ch}
        if self.wlan is not None:
            try:
                msg["rssi"] = self.wlan.status("rssi")
            except Exception:                         # noqa: BLE001
                pass
        if self.env:
            t, rh, p = self.env
            msg["env"] = {"t": round(t, 1), "rh": round(rh, 1), "p": round(p, 0)}
        if self.cfg.IS_FAN_NODE:
            msg["fan"] = self.fan.telemetry()
        return msg

    def info(self):
        return {"node": self.cfg.NODE_ID, "t": "info",
                "ip": self.wlan.ifconfig()[0] if self.wlan else "",
                "display": bool(self.screen),
                "fan_output": self.fan.enabled,
                "channels": [{"name": c.name, "mux": c.port, "type": c.kind,
                              "offset": round(c.offset, 3), "ok": c.ok} for c in self.channels]}

    # ---------------- main loop ----------------
    def run(self):
        cfg = self.cfg
        self.start_display()
        self.wlan = connect_wifi(cfg.WIFI_SSID, cfg.WIFI_PASSWORD, "lumosair-" + cfg.NODE_ID,
                                 log=self.log)
        self.link = Link(cfg, self.log)
        self.link.connect_mqtt(self.handle)
        if self.screen:
            self.screen.layout()
        wdt = WDT(timeout=cfg.WATCHDOG_MS) if (WDT and cfg.WATCHDOG_MS) else None

        while True:
            now = ticks_ms()
            if wdt:
                wdt.feed()

            for ch in self.channels:
                ch.sample(self.zeroing)

            if self.zeroing is not None and ticks_diff(now, self.zero_start) > 3000:
                self.finish_zero()

            if self.bme and ticks_diff(now, self._last_env) >= cfg.ENV_INTERVAL_MS:
                self._last_env = now
                try:
                    self.env = self.bme.read()
                except Exception:                     # noqa: BLE001
                    self.env = None

            if ticks_diff(now, self._last_pub) >= cfg.PUBLISH_INTERVAL_MS:
                self._last_pub = now
                self.link.publish(self.telemetry())
                if self.led:
                    self.led.value(1 if all(c.ok for c in self.channels) else not self.led.value())

            self.link.poll_commands(self.handle)
            status = self.link.poll_status()
            if status and (status.get("fan") or {}).get("level") is not None:
                self.bench_level = status["fan"]["level"]

            if self.screen and ticks_diff(now, self._last_draw) >= cfg.DISPLAY_INTERVAL_MS:
                self._last_draw = now
                self.draw(status)

            sleep_ms(cfg.SAMPLE_INTERVAL_MS)

    def draw(self, status):
        s = self.screen
        fan = (status or {}).get("fan") or {}
        if status:
            s.status(status.get("sev", "ok"),
                     ip=self.wlan.ifconfig()[0] if self.wlan else None)
            s.flow(status.get("cfm"), status.get("src", ""))
            s.fan(fan.get("level", self.fan.level), fan.get("mode", "manual"), fan.get("rec"))
            s.headline(status.get("msg", ""), status.get("sev", "ok"))
        else:
            s.status("stale", ip=self.wlan.ifconfig()[0] if self.wlan else None)
            s.flow(None, "no link to PC")
            s.fan(self.fan.level if self.cfg.IS_FAN_NODE else None, self.fan.mode, None)
            ok = sum(1 for c in self.channels if c.ok)
            s.headline("PC app not running. Sensors %d/%d OK" % (ok, len(self.channels)),
                       "stale")
        s.channels([(c.name, c.last_pa if c.last_pa is not None else 0.0, c.ok)
                    for c in self.channels])

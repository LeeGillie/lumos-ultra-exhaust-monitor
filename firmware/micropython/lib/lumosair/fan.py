"""Fan speed output for the AC Infinity CLOUDLINE UIS port.

SAFETY / HONESTY NOTE
--------------------
The UIS connector pinout is community-reverse-engineered, not published by
AC Infinity. This module therefore starts DISABLED: it tracks the level the PC
asks for and reports it in telemetry, but drives no pin until you set
FAN_OUTPUT_ENABLED = True in config.py, having checked the pinout with a meter
or scope. With it disabled the whole automatic-control path can still be tested
end to end — you just move the dial yourself.

Two output styles are supported:
  * "pwm"    PWM on a GPIO (level 1-10 -> duty), the usual UIS approach
  * "dac"    0-10 V style analogue on GPIO25/26 via the ESP32 DAC, for fans
             that take an analogue speed input (needs a level shifter)
"""

try:
    from machine import Pin, PWM, DAC
except ImportError:                                   # host tests
    Pin = PWM = DAC = None


class FanOutput:
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.level = cfg.FAN_DEFAULT_LEVEL
        self.mode = "manual"
        self._out = None
        self.enabled = bool(getattr(cfg, "FAN_OUTPUT_ENABLED", False))
        if not self.enabled or Pin is None:
            return
        try:
            if cfg.FAN_OUTPUT_KIND == "pwm":
                self._out = PWM(Pin(cfg.FAN_OUTPUT_PIN), freq=cfg.FAN_PWM_FREQ)
            elif cfg.FAN_OUTPUT_KIND == "dac":
                self._out = DAC(Pin(cfg.FAN_OUTPUT_PIN))
            self.apply(self.level)
        except Exception as e:                        # noqa: BLE001
            self.log("fan output init failed:", e)
            self._out = None
            self.enabled = False

    def duty_for(self, level):
        """Level 1..levels mapped onto the configured duty window."""
        levels = self.cfg.FAN_LEVELS
        level = max(0, min(levels, int(level)))
        if level == 0:
            return 0.0
        lo, hi = self.cfg.FAN_DUTY_MIN, self.cfg.FAN_DUTY_MAX
        return lo + (hi - lo) * (level - 1) / float(levels - 1)

    def apply(self, level):
        """Set the level. Returns True when a pin was actually driven."""
        self.level = max(0, min(self.cfg.FAN_LEVELS, int(level)))
        if not self._out:
            return False
        frac = self.duty_for(self.level)
        try:
            if self.cfg.FAN_OUTPUT_KIND == "pwm":
                self._out.duty_u16(int(frac * 65535))
            else:
                self._out.write(int(frac * 255))
            return True
        except Exception as e:                        # noqa: BLE001
            self.log("fan output write failed:", e)
            return False

    def telemetry(self):
        return {"level": self.level, "mode": self.mode, "driven": bool(self._out)}

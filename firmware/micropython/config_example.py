"""Copy to config.py on the node and edit. config.py is git-ignored.

Both boxes run the same firmware and the same enclosure; only this file differs.
"""

# ---------------- identity ----------------
NODE_ID = "laser"              # "laser" or "fan" — must match the PC app's system.json
IS_FAN_NODE = False            # the fan node reports (and may drive) the fan level

# ---------------- Wi-Fi ----------------
WIFI_SSID = "your-ssid"
WIFI_PASSWORD = "your-password"

# ---------------- transport ----------------
UDP_TARGET = "255.255.255.255"   # or the PC's IP for unicast
UDP_PORT = 47810                 # telemetry out
UDP_COMMAND_PORT = 47811         # commands in
UDP_STATUS_PORT = 47812          # status broadcast from the PC app (drives the display)

MQTT_ENABLED = False             # needs umqtt.simple on the node
MQTT_HOST = "homeassistant.local"
MQTT_PORT = 1883
MQTT_USER = ""
MQTT_PASSWORD = ""
MQTT_TOPIC_ROOT = "lumosair"

OTA_URL = "http://192.168.1.50:8123"   # PC running tools/serve_update.py

# ---------------- timing (ms) ----------------
SAMPLE_INTERVAL_MS = 50
PUBLISH_INTERVAL_MS = 250
DISPLAY_INTERVAL_MS = 500
ENV_INTERVAL_MS = 2000
WATCHDOG_MS = 20000              # 0 disables the watchdog

# ---------------- bench mode ----------------
# No sensors wired? Report what the app's model predicts at the current fan level
# instead (lib/lumosair/benchsim.py). Telemetry, display and commands stay real.
# Never leave this on in an installed box.
BENCH_SIMULATE = False
BENCH_PROFILE = "A"              # "A" (separator at the laser) or "C" (today's system)
# ---------------- I2C / sensors ----------------
I2C_SDA = 21
I2C_SCL = 22
I2C_HZ = 100_000                 # keep it slow: sensor leads can be 1–2 m
TCA9548A_ADDR = 0x70             # 0 when only one sensor is fitted (fan box)
HAS_BME280 = True
BME280_ADDR = 0x76
STATUS_LED = 2                   # None to disable

# Channel names must match "channel" in the PC app's system.json.
# sign = +1 when the sensor's + port is on the higher-pressure tap.
# XGZP k: below 1 kPa -> 8192, a ±1 kPa part -> 4096 (datasheet range table).
if NODE_ID == "fan":
    CHANNELS = (
        {"name": "fan_in", "mux": 0, "type": "xgzp", "k": 4096, "sign": 1},
    )
else:
    CHANNELS = (
        {"name": "cyc_dp", "mux": 0, "type": "sdp810", "sign": 1},   # + inlet tap, − outlet tap
        {"name": "bin",    "mux": 1, "type": "xgzp", "k": 4096, "sign": 1},
        {"name": "pitot",  "mux": 2, "type": "sdp810", "sign": 1},   # + total, − static
        {"name": "run_in", "mux": 3, "type": "xgzp", "k": 4096, "sign": 1},
        {"name": "encl",   "mux": 4, "type": "sdp810", "sign": 1},
    )

# ---------------- display (NULLLAB 2.0" ST7789, 240x320) ----------------
HAS_DISPLAY = True
DISPLAY_SPI = 1                  # HSPI
DISPLAY_SCK = 14
DISPLAY_MOSI = 13
DISPLAY_CS = 15
DISPLAY_DC = 27
DISPLAY_RST = None               # module pulls RES high itself
DISPLAY_BL = None                # module pulls BLK high itself
DISPLAY_BAUD = 30_000_000
DISPLAY_ROTATION = 1             # 1 = landscape, 320x240

# ---------------- fan output (fan node only) ----------------
# The CLOUDLINE UIS pinout is community-reverse-engineered, so this stays off
# until you have checked it yourself. With it off, the node still reports the
# level the app asks for and the app still tells you what to set.
FAN_OUTPUT_ENABLED = False
FAN_OUTPUT_KIND = "pwm"          # "pwm" or "dac"
FAN_OUTPUT_PIN = 25
FAN_PWM_FREQ = 1000
FAN_DUTY_MIN = 0.10              # duty at level 1
FAN_DUTY_MAX = 1.00              # duty at level 10
FAN_LEVELS = 10
FAN_DEFAULT_LEVEL = 10

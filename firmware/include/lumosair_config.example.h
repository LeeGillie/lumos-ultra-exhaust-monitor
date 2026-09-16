// Copy this file to lumosair_config.h (same folder) and edit. lumosair_config.h is git-ignored.
#pragma once
#include "channels.h"

// ---------- Wi-Fi ----------
#define WIFI_SSID     "your-ssid"
#define WIFI_PASSWORD "your-password"
#define OTA_PASSWORD  "lumosair"          // ArduinoOTA password

// ---------- Transport ----------
// UDP: nodes broadcast JSON; the PC app listens. No broker needed.
#define UDP_ENABLED        1
#define UDP_TARGET         "255.255.255.255"  // or the PC's IP for unicast
#define UDP_PORT           47810
#define UDP_COMMAND_PORT   47811

// MQTT: optional, e.g. the Home Assistant Mosquitto add-on.
#define MQTT_ENABLED       0
#define MQTT_HOST          "homeassistant.local"
#define MQTT_PORT          1883
#define MQTT_USER          ""
#define MQTT_PASSWORD      ""
#define MQTT_TOPIC_ROOT    "lumosair"

// ---------- Timing ----------
#define SAMPLE_INTERVAL_MS   50    // sensor read rate (each reading is averaged by the SDP8xx itself)
#define PUBLISH_INTERVAL_MS  250   // telemetry rate
#define ENV_INTERVAL_MS      2000  // BME280 rate

// ---------- Hardware ----------
#define I2C_SDA      21
#define I2C_SCL      22
#define I2C_HZ       100000        // keep 100 kHz: sensor leads can be 1–2 m
#define TCA9548A_ADDR 0x70         // set to 0 if you have only one sensor and no multiplexer
#define STATUS_LED   2
#define HAS_BME280   1             // BME280 on the main bus (not behind the mux)
#define BME280_ADDR  0x76

// ---------- Node identity & sensors ----------
// Channel names must match "channel" in the PC app's system.json.
// Sign: +1 when the sensor's (+) port is on the higher-pressure tap (room side for suction channels).
#if defined(NODE_FAN)
  #define NODE_ID "fan"
  static const ChannelDef CHANNELS[] = {
    // name      mux  sensor          sign  xgzpK
    { "fan_in",  0,   SENSOR_XGZP6897D, +1, 4096 },  // ±1 kPa part: suction here can exceed 500 Pa
  };
#else
  #define NODE_ID "laser"
  static const ChannelDef CHANNELS[] = {
    { "cyc_dp",  0,   SENSOR_SDP810,  +1,   0 },   // + cyclone inlet tap, − cyclone outlet tap
    { "bin",     1,   SENSOR_XGZP6897D, +1, 4096 }, // + room, − dust bin lid   (±1 kPa part)
    { "pitot",   2,   SENSOR_SDP810,  +1,   0 },   // + pitot total, − pitot static
    { "run_in",  3,   SENSOR_XGZP6897D, +1, 4096 }, // + room, − 6" run start  (±1 kPa part)
    { "encl",    4,   SENSOR_SDP810,  +1,   0 },   // + room, − inside laser enclosure
    // XGZP6897D scale K from the datasheet table: range < 1 kPa → 8192, 1–2 kPa (±1 kPa part) → 4096.
    // Precise SDP810-500Pa parts are used where the signal is small (pitot, enclosure) or drives flow (cyclone ΔP).
  };
#endif

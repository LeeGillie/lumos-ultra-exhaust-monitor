// LumosAir sensor node
// Reads differential-pressure sensors (behind a TCA9548A) and an optional BME280,
// publishes JSON telemetry over UDP broadcast and/or MQTT, and accepts commands:
//   {"cmd":"zero"}        fan OFF first: average 3 s and store per-channel offsets in NVS
//   {"cmd":"clear_zero"}  remove stored offsets
//   {"cmd":"reboot"}
//   {"cmd":"info"}        publish a one-off info packet
//
// Telemetry payload (topic <root>/<node>/telemetry or UDP port 47810):
//   {"node":"laser","seq":12,"up":3456,"rssi":-61,
//    "ch":{"cyc_dp":{"pa":212.4,"t":24.1,"ok":true}, ...},
//    "env":{"t":23.9,"rh":41.0,"p":94412.0}}

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ArduinoOTA.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <esp_task_wdt.h>

#if __has_include("lumosair_config.h")
  #include "lumosair_config.h"
#else
  #warning "include/lumosair_config.h not found - using lumosair_config.example.h (edit Wi-Fi settings!)"
  #include "lumosair_config.example.h"
#endif
#include "sensors.h"

#if HAS_BME280
  #include <Adafruit_BME280.h>
  static Adafruit_BME280 bme;
  static bool bmeOk = false;
#endif

static const size_t NUM_CHANNELS = sizeof(CHANNELS) / sizeof(CHANNELS[0]);

struct ChannelState {
  bool initialized = false;
  bool ok = false;
  float sumPa = 0;       // accumulated since last publish
  float sumT = 0;
  uint16_t count = 0;
  float lastPa = NAN;
  float lastT = NAN;
  float offset = 0;
  uint32_t lastInitAttempt = 0;
  uint16_t errors = 0;
};

static ChannelState state[8];
static I2CMux mux(TCA9548A_ADDR);
static WiFiUDP udp;
static WiFiUDP cmdUdp;
static WiFiClient mqttNet;
static PubSubClient mqtt(mqttNet);
static Preferences prefs;

static uint32_t seq = 0;
static uint32_t lastSample = 0, lastPublish = 0, lastEnv = 0;
[[maybe_unused]] static uint32_t lastMqttAttempt = 0;
static float envT = NAN, envRh = NAN, envP = NAN;

// Zeroing state
static bool zeroing = false;
static uint32_t zeroStart = 0;
static float zeroSum[8];
static uint16_t zeroCount[8];

// ------------------------------------------------------------------ sensors

static bool initChannel(size_t i) {
  const ChannelDef& c = CHANNELS[i];
  state[i].lastInitAttempt = millis();
  if (!mux.select(c.muxPort)) return false;
  bool ok = c.type == SENSOR_SDP810 ? sdp8xx::begin() : xgzp::begin();
  state[i].initialized = ok;
  return ok;
}

static void sampleChannels() {
  for (size_t i = 0; i < NUM_CHANNELS; i++) {
    const ChannelDef& c = CHANNELS[i];
    ChannelState& s = state[i];
    if (!s.initialized) {
      if (millis() - s.lastInitAttempt > 5000) initChannel(i);
      if (!s.initialized) { s.ok = false; continue; }
    }
    float pa = NAN, t = NAN;
    bool ok = mux.select(c.muxPort) &&
              (c.type == SENSOR_SDP810 ? sdp8xx::read(pa, t) : xgzp::read(c.xgzpK, pa, t));
    if (!ok) {
      if (++s.errors >= 10) {        // persistent failure: re-initialise
        s.initialized = false;
        s.ok = false;
        s.errors = 0;
        mux.invalidate();
      }
      continue;
    }
    s.errors = 0;
    s.ok = true;
    pa = pa * c.sign;
    if (zeroing) {
      zeroSum[i] += pa;
      zeroCount[i]++;
    }
    pa -= s.offset;
    s.sumPa += pa;
    s.sumT += t;
    s.count++;
  }
}

static void sampleEnv() {
#if HAS_BME280
  if (!bmeOk) return;
  float t = bme.readTemperature();
  float rh = bme.readHumidity();
  float p = bme.readPressure();
  if (!isnan(t) && !isnan(p) && p > 50000) { envT = t; envRh = rh; envP = p; }
#endif
}

// ------------------------------------------------------------------ zero offsets

static void loadOffsets() {
  prefs.begin("lumosair", true);
  for (size_t i = 0; i < NUM_CHANNELS; i++)
    state[i].offset = prefs.getFloat(CHANNELS[i].name, 0.0f);
  prefs.end();
}

static void startZero() {
  zeroing = true;
  zeroStart = millis();
  for (size_t i = 0; i < NUM_CHANNELS; i++) { zeroSum[i] = 0; zeroCount[i] = 0; }
  Serial.println("Zeroing: keep the fan off for 3 s...");
}

static void finishZero() {
  zeroing = false;
  prefs.begin("lumosair", false);
  for (size_t i = 0; i < NUM_CHANNELS; i++) {
    if (zeroCount[i] < 10) continue;
    float off = zeroSum[i] / zeroCount[i];
    if (fabs(off) > 20.0f) {  // a real offset is < ~2 Pa; bigger means air was moving
      Serial.printf("  %s: %.2f Pa looks like airflow, not offset - skipped\n", CHANNELS[i].name, off);
      continue;
    }
    state[i].offset = off;
    prefs.putFloat(CHANNELS[i].name, off);
    Serial.printf("  %s offset %.3f Pa\n", CHANNELS[i].name, off);
  }
  prefs.end();
}

static void clearZero() {
  prefs.begin("lumosair", false);
  prefs.clear();
  prefs.end();
  for (size_t i = 0; i < NUM_CHANNELS; i++) state[i].offset = 0;
}

// ------------------------------------------------------------------ networking

static void publishRaw(const char* suffix, const String& payload) {
#if UDP_ENABLED
  if (strcmp(suffix, "telemetry") == 0 && WiFi.isConnected()) {
    udp.beginPacket(UDP_TARGET, UDP_PORT);
    udp.write((const uint8_t*)payload.c_str(), payload.length());
    udp.endPacket();
  }
#endif
#if MQTT_ENABLED
  if (mqtt.connected()) {
    String topic = String(MQTT_TOPIC_ROOT) + "/" + NODE_ID + "/" + suffix;
    mqtt.publish(topic.c_str(), payload.c_str());
  }
#endif
}

static void publishTelemetry() {
  JsonDocument doc;
  doc["node"] = NODE_ID;
  doc["seq"] = ++seq;
  doc["up"] = millis();
  doc["rssi"] = WiFi.RSSI();
  JsonObject ch = doc["ch"].to<JsonObject>();
  for (size_t i = 0; i < NUM_CHANNELS; i++) {
    ChannelState& s = state[i];
    JsonObject o = ch[CHANNELS[i].name].to<JsonObject>();
    if (s.count > 0) {
      s.lastPa = s.sumPa / s.count;
      s.lastT = s.sumT / s.count;
      s.sumPa = s.sumT = 0;
      s.count = 0;
      o["pa"] = serialized(String(s.lastPa, 2));
      o["t"] = serialized(String(s.lastT, 1));
      o["ok"] = true;
    } else {
      o["ok"] = false;
    }
  }
  if (!isnan(envP)) {
    JsonObject e = doc["env"].to<JsonObject>();
    e["t"] = serialized(String(envT, 1));
    e["rh"] = serialized(String(envRh, 1));
    e["p"] = serialized(String(envP, 0));
  }
  String out;
  serializeJson(doc, out);
  publishRaw("telemetry", out);
}

static void publishInfo() {
  JsonDocument doc;
  doc["node"] = NODE_ID;
  doc["ip"] = WiFi.localIP().toString();
  doc["fw"] = __DATE__ " " __TIME__;
  JsonArray arr = doc["channels"].to<JsonArray>();
  for (size_t i = 0; i < NUM_CHANNELS; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["name"] = CHANNELS[i].name;
    o["mux"] = CHANNELS[i].muxPort;
    o["type"] = CHANNELS[i].type == SENSOR_SDP810 ? "SDP810" : "XGZP6897D";
    o["offset"] = state[i].offset;
    o["ok"] = state[i].ok;
  }
  String out;
  serializeJson(doc, out);
  publishRaw("info", out);
  Serial.println(out);
}

static void handleCommand(const char* json, size_t len) {
  JsonDocument doc;
  if (deserializeJson(doc, json, len)) return;
  const char* cmd = doc["cmd"] | "";
  Serial.printf("Command: %s\n", cmd);
  if (strcmp(cmd, "zero") == 0) startZero();
  else if (strcmp(cmd, "clear_zero") == 0) clearZero();
  else if (strcmp(cmd, "info") == 0) publishInfo();
  else if (strcmp(cmd, "reboot") == 0) { delay(100); ESP.restart(); }
}

[[maybe_unused]] static void onMqtt(char* topic, byte* payload, unsigned int len) {
  handleCommand((const char*)payload, len);
}

static void ensureMqtt() {
#if MQTT_ENABLED
  if (mqtt.connected() || !WiFi.isConnected()) return;
  if (millis() - lastMqttAttempt < 5000) return;
  lastMqttAttempt = millis();
  String id = String("lumosair-") + NODE_ID;
  String status = String(MQTT_TOPIC_ROOT) + "/" + NODE_ID + "/status";
  const char* user = strlen(MQTT_USER) ? MQTT_USER : nullptr;
  const char* pass = strlen(MQTT_PASSWORD) ? MQTT_PASSWORD : nullptr;
  if (mqtt.connect(id.c_str(), user, pass, status.c_str(), 0, true, "offline")) {
    mqtt.publish(status.c_str(), "online", true);
    String cmdTopic = String(MQTT_TOPIC_ROOT) + "/" + NODE_ID + "/cmd";
    mqtt.subscribe(cmdTopic.c_str());
    Serial.println("MQTT connected");
  }
#endif
}

static void pollUdpCommands() {
  int size = cmdUdp.parsePacket();
  if (size <= 0) return;
  char buf[256];
  int n = cmdUdp.read(buf, sizeof(buf) - 1);
  if (n > 0) { buf[n] = 0; handleCommand(buf, n); }
}

static void setupWifi() {
  static const String hostname = String("lumosair-") + NODE_ID;
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(hostname.c_str());
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);  // lower latency, steadier UDP
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Wi-Fi");
  for (int i = 0; i < 40 && !WiFi.isConnected(); i++) { delay(250); Serial.print('.'); }
  if (WiFi.isConnected()) Serial.printf(" connected: %s\n", WiFi.localIP().toString().c_str());
  else Serial.println(" not yet (will keep trying)");
}

// ------------------------------------------------------------------ main

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("\nLumosAir node '%s', %u channel(s)\n", NODE_ID, (unsigned)NUM_CHANNELS);
  pinMode(STATUS_LED, OUTPUT);

  Wire.begin(I2C_SDA, I2C_SCL, I2C_HZ);
  Wire.setTimeOut(20);

#if HAS_BME280
  bmeOk = bme.begin(BME280_ADDR, &Wire);
  Serial.printf("BME280: %s\n", bmeOk ? "ok" : "not found");
#endif

  loadOffsets();
  for (size_t i = 0; i < NUM_CHANNELS; i++) {
    bool ok = initChannel(i);
    Serial.printf("  %-8s mux %u  %s  offset %.3f\n", CHANNELS[i].name, CHANNELS[i].muxPort, ok ? "ok" : "NOT FOUND", state[i].offset);
  }

  setupWifi();
  udp.begin(0);
  cmdUdp.begin(UDP_COMMAND_PORT);
#if MQTT_ENABLED
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setBufferSize(1024);
#endif

  ArduinoOTA.setHostname((String("lumosair-") + NODE_ID).c_str());
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.begin();

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t wdt = { .timeout_ms = 10000, .idle_core_mask = 0, .trigger_panic = true };
  esp_task_wdt_reconfigure(&wdt);
#else
  esp_task_wdt_init(10, true);
#endif
  esp_task_wdt_add(nullptr);
}

void loop() {
  uint32_t now = millis();
  esp_task_wdt_reset();
  ArduinoOTA.handle();

  if (now - lastSample >= SAMPLE_INTERVAL_MS) { lastSample = now; sampleChannels(); }
  if (now - lastEnv >= ENV_INTERVAL_MS) { lastEnv = now; sampleEnv(); }
  if (zeroing && now - zeroStart >= 3000) { finishZero(); publishInfo(); }

  if (now - lastPublish >= PUBLISH_INTERVAL_MS) {
    lastPublish = now;
    publishTelemetry();
    // LED: solid = Wi-Fi ok and all sensors ok; blinking = problem
    bool allOk = WiFi.isConnected();
    for (size_t i = 0; i < NUM_CHANNELS; i++) allOk &= state[i].ok;
    digitalWrite(STATUS_LED, allOk ? HIGH : !digitalRead(STATUS_LED));
  }

  ensureMqtt();
#if MQTT_ENABLED
  mqtt.loop();
#endif
  pollUdpCommands();
  delay(2);
}

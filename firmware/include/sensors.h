#pragma once
#include <Arduino.h>
#include <Wire.h>
#include "channels.h"

// ---------------- TCA9548A multiplexer ----------------
class I2CMux {
 public:
  explicit I2CMux(uint8_t addr) : addr_(addr) {}
  bool select(uint8_t port) {
    if (addr_ == 0) return true;
    if (port == current_) return true;
    Wire.beginTransmission(addr_);
    Wire.write(uint8_t(1u << port));
    bool ok = Wire.endTransmission() == 0;
    current_ = ok ? port : 0xFF;
    return ok;
  }
  void invalidate() { current_ = 0xFF; }
 private:
  uint8_t addr_;
  uint8_t current_ = 0xFF;
};

// ---------------- Sensirion SDP8xx ----------------
// Datasheet: "SDP8xx-Digital" v1.1. Continuous mode, differential pressure, temperature-compensated,
// average-till-read (0x3615). Each read returns DP, T and the scale factor, each with CRC-8 (0x31, init 0xFF).
namespace sdp8xx {
  const uint8_t ADDR = 0x25;

  inline uint8_t crc8(const uint8_t* data, size_t len) {
    uint8_t crc = 0xFF;
    for (size_t i = 0; i < len; i++) {
      crc ^= data[i];
      for (int b = 0; b < 8; b++) crc = (crc & 0x80) ? uint8_t((crc << 1) ^ 0x31) : uint8_t(crc << 1);
    }
    return crc;
  }

  inline bool command(uint16_t cmd) {
    Wire.beginTransmission(ADDR);
    Wire.write(uint8_t(cmd >> 8));
    Wire.write(uint8_t(cmd & 0xFF));
    return Wire.endTransmission() == 0;
  }

  inline bool begin() {
    command(0x3FF9);          // stop any running measurement (may NACK if idle)
    delay(2);
    if (!command(0x3615)) return false;  // start continuous DP, averaging
    delay(25);                // first valid value after ~20 ms
    return true;
  }

  // Returns false on I2C or CRC error.
  inline bool read(float& pa, float& tempC) {
    if (Wire.requestFrom(ADDR, uint8_t(9)) != 9) return false;
    uint8_t b[9];
    for (int i = 0; i < 9; i++) b[i] = Wire.read();
    for (int i = 0; i < 9; i += 3)
      if (crc8(b + i, 2) != b[i + 2]) return false;
    int16_t dp = int16_t((b[0] << 8) | b[1]);
    int16_t t = int16_t((b[3] << 8) | b[4]);
    uint16_t scale = uint16_t((b[6] << 8) | b[7]);
    if (scale == 0) return false;
    pa = float(dp) / float(scale);
    tempC = float(t) / 200.0f;
    return true;
  }
}

// ---------------- CFSensor XGZP6897D ----------------
// Register map per datasheet: 0x30 CMD (0x0A = combined P+T conversion, bit3 = SCO busy),
// 0x06..0x08 pressure (24-bit two's complement), 0x09..0x0A temperature (16-bit, /256 °C).
// Pa = raw / K, K depends on the part's range (see the datasheet table).
namespace xgzp {
  const uint8_t ADDR = 0x6D;

  inline bool writeReg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(ADDR);
    Wire.write(reg);
    Wire.write(val);
    return Wire.endTransmission() == 0;
  }

  inline bool readReg(uint8_t reg, uint8_t* out, uint8_t n) {
    Wire.beginTransmission(ADDR);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(ADDR, n) != n) return false;
    for (uint8_t i = 0; i < n; i++) out[i] = Wire.read();
    return true;
  }

  inline bool begin() { return writeReg(0x30, 0x0A); }

  inline bool read(uint16_t k, float& pa, float& tempC) {
    if (k == 0) return false;
    if (!writeReg(0x30, 0x0A)) return false;
    uint32_t start = millis();
    uint8_t cmd = 0x08;
    while (millis() - start < 30) {
      if (!readReg(0x30, &cmd, 1)) return false;
      if ((cmd & 0x08) == 0) break;
      delay(2);
    }
    if (cmd & 0x08) return false;
    uint8_t b[5];
    if (!readReg(0x06, b, 5)) return false;
    int32_t raw = (int32_t(b[0]) << 16) | (int32_t(b[1]) << 8) | b[2];
    if (raw & 0x800000) raw -= 0x1000000;
    int16_t t = int16_t((b[3] << 8) | b[4]);
    pa = float(raw) / float(k);
    tempC = float(t) / 256.0f;
    return true;
  }
}

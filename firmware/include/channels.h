#pragma once
#include <Arduino.h>

enum SensorType : uint8_t {
  SENSOR_SDP810 = 0,     // Sensirion SDP810-500Pa / SDP810-125Pa, I2C 0x25
  SENSOR_XGZP6897D = 1,  // CFSensor XGZP6897D, I2C 0x6D
};

struct ChannelDef {
  const char* name;
  uint8_t muxPort;       // TCA9548A port 0..7 (ignored when TCA9548A_ADDR == 0)
  SensorType type;
  int8_t sign;           // +1 or -1
  uint16_t xgzpK;        // XGZP6897D scale divisor K (from datasheet, depends on range)
};

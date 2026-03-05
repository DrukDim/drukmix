#pragma once
#include <cstdint>

namespace DrukMixPump::Cfg {
  static constexpr uint8_t  PROTO = 1;
  static constexpr int      WIFI_CHANNEL = 6;

  static constexpr uint32_t CMD_TIMEOUT_MS   = 1300;
  static constexpr uint32_t STATUS_PERIOD_MS = 200;
  static constexpr uint32_t DIR_DEAD_MS      = 80;

  static constexpr uint32_t SPI_HZ = 1000000;

  // Flags (from agent)
  static constexpr uint8_t FLAG_REV  = 0x01;
  static constexpr uint8_t FLAG_STOP = 0x02;
  static constexpr uint8_t FLAG_AUTO = 0x04;

  // Pump model
  static constexpr int32_t PUMP_MAX_MILLI_LPM_DEFAULT = 10000;
  static constexpr int32_t PUMP_MIN_MILLI_LPM_DEFAULT = 200;
}
#pragma once
#include <Arduino.h>

struct ModbusConfig {
  uint16_t slave_id = 1;
  uint32_t baud = 9600;
  uint32_t timeout_ms = 120;
};

struct PollConfig {
  bool enabled = true;
  uint32_t interval_ms = 1000;
};

struct SystemConfig {
  String active_preset = "runtime";
  uint32_t schema_version = 1;
};

class ConfigStore {
public:
  bool begin();

  bool load_modbus_config(ModbusConfig* out);
  bool save_modbus_config(const ModbusConfig& cfg);

  bool load_poll_config(PollConfig* out);
  bool save_poll_config(const PollConfig& cfg);

  bool load_system_config(SystemConfig* out);
  bool save_system_config(const SystemConfig& cfg);
};

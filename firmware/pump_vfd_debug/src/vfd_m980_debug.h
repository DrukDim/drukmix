#pragma once
#include <stdint.h>
#include "rs485_modbus.h"
#include "config_store.h"

struct RuntimeSnapshot {
  bool valid = false;
  uint16_t run_state = 0;
  uint16_t fault_code = 0;
  int16_t actual_freq_x10 = 0;
  int16_t actual_speed_raw = 0;
  uint16_t output_current_x10 = 0;
  uint16_t di_state = 0;
};

struct ModeSwitchSnapshot {
  bool valid = false;
  uint16_t f0_00 = 0;
  uint16_t f0_01 = 0;
  uint16_t f0_18 = 0;
  uint16_t f0_20 = 0;
  uint16_t f1_05 = 0;
  uint16_t f1_06 = 0;
  uint16_t u0_11 = 0;
};

struct ModbusSnapshot {
  bool valid = false;
  uint16_t f7_00 = 0;
  uint16_t f7_01 = 0;
  uint16_t f7_02 = 0;
  uint16_t f7_03 = 0;
};

class VfdM980Debug {
public:
  void begin();
  void apply_modbus_config(const ModbusConfig& cfg);
  ModbusConfig modbus_config() const;
  bool read_reg(uint16_t reg, uint16_t* value);
  bool read_block(uint16_t reg, uint16_t count, uint16_t* out);
  bool write_reg(uint16_t reg, uint16_t value);

  bool read_runtime_snapshot(RuntimeSnapshot* st);
  bool read_mode_switch_snapshot(ModeSwitchSnapshot* st);
  bool read_modbus_snapshot(ModbusSnapshot* st);

private:
  Rs485Modbus modbus_;
  ModbusConfig cfg_{};
};

#include "vfd_m980_driver.h"
#include <Arduino.h>
#include "pump_vfd_config.h"

// M980 Modbus map
static constexpr uint16_t REG_CMD_FREQ    = 0x0001;
static constexpr uint16_t REG_CMD_CONTROL = 0x0002;

static constexpr uint16_t REG_RUN_STATE   = 0x1000;
static constexpr uint16_t REG_FAULT_CODE  = 0x1001;
static constexpr uint16_t REG_RUN_FREQ    = 0x1003;
static constexpr uint16_t REG_RUN_SPEED   = 0x1004;
static constexpr uint16_t REG_OUT_CURRENT = 0x1006;

void VfdM980Driver::begin() {
  modbus_.begin();
}

bool VfdM980Driver::set_run_forward() {
  return modbus_.write_single_register(MODBUS_SLAVE_ID, REG_CMD_CONTROL, 1);
}

bool VfdM980Driver::set_stop_ramp() {
  return modbus_.write_single_register(MODBUS_SLAVE_ID, REG_CMD_CONTROL, 6);
}

bool VfdM980Driver::reset_fault() {
  return clear_fault_sequence_();
}

bool VfdM980Driver::set_frequency_pct_x100(uint16_t value) {
  if (value > 10000) value = 10000;
  return modbus_.write_single_register(MODBUS_SLAVE_ID, REG_CMD_FREQ, value);
}

bool VfdM980Driver::poll_status(VfdStatus* st) {
  if (!st) return false;

  // Read one contiguous block: 0x1000..0x1006
  // Used registers:
  // 0 -> 0x1000 RUN_STATE
  // 1 -> 0x1001 FAULT_CODE
  // 3 -> 0x1003 RUN_FREQ
  // 4 -> 0x1004 RUN_SPEED
  // 6 -> 0x1006 OUT_CURRENT
  uint16_t regs[7] = {0};

  if (!modbus_.read_holding_registers(MODBUS_SLAVE_ID, REG_RUN_STATE, 7, regs)) return false;

  st->online = true;
  st->running = (regs[0] != 0);
  st->fault_code = regs[1];
  st->actual_freq_x10 = (int16_t)regs[3];
  st->actual_speed_raw = (int16_t)regs[4];
  st->output_current_x10 = regs[6];
  return true;
}



bool VfdM980Driver::clear_fault_sequence_() {
  bool ok1 = modbus_.write_single_register(MODBUS_SLAVE_ID, REG_CMD_CONTROL, 6);
  delay(200);

  bool ok2 = modbus_.write_single_register(MODBUS_SLAVE_ID, REG_CMD_CONTROL, 7);
  delay(350);

  bool ok3 = modbus_.write_single_register(MODBUS_SLAVE_ID, REG_CMD_CONTROL, 6);
  delay(200);

  Serial.print("[DRV] clear_fault_sequence stop1=");
  Serial.print(ok1 ? 1 : 0);
  Serial.print(" reset=");
  Serial.print(ok2 ? 1 : 0);
  Serial.print(" stop2=");
  Serial.println(ok3 ? 1 : 0);

  return ok1 && ok2 && ok3;
}

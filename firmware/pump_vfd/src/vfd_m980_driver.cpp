#include "vfd_m980_driver.h"
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
  return modbus_.write_single_register(MODBUS_SLAVE_ID, REG_CMD_CONTROL, 7);
}

bool VfdM980Driver::set_frequency_pct_x100(uint16_t value) {
  if (value > 10000) value = 10000;
  return modbus_.write_single_register(MODBUS_SLAVE_ID, REG_CMD_FREQ, value);
}

bool VfdM980Driver::poll_status(VfdStatus* st) {
  if (!st) return false;

  uint16_t regs[5] = {0};

  if (!modbus_.read_holding_registers(MODBUS_SLAVE_ID, REG_RUN_STATE, 1, &regs[0])) return false;
  if (!modbus_.read_holding_registers(MODBUS_SLAVE_ID, REG_FAULT_CODE, 1, &regs[1])) return false;
  if (!modbus_.read_holding_registers(MODBUS_SLAVE_ID, REG_RUN_FREQ, 1, &regs[2])) return false;
  if (!modbus_.read_holding_registers(MODBUS_SLAVE_ID, REG_RUN_SPEED, 1, &regs[3])) return false;
  if (!modbus_.read_holding_registers(MODBUS_SLAVE_ID, REG_OUT_CURRENT, 1, &regs[4])) return false;

  st->online = true;
  st->running = (regs[0] != 0);
  st->fault_code = regs[1];
  st->actual_freq_x10 = (int16_t)regs[2];
  st->actual_speed_raw = (int16_t)regs[3];
  st->output_current_x10 = regs[4];
  return true;
}

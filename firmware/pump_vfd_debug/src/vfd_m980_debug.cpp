#include "vfd_m980_debug.h"
#include "debug_config.h"

static constexpr uint16_t REG_CMD_FREQ    = 0x0001;
static constexpr uint16_t REG_CMD_CONTROL = 0x0002;

static constexpr uint16_t REG_RUN_STATE   = 0x1000;
static constexpr uint16_t REG_FAULT_CODE  = 0x1001;
static constexpr uint16_t REG_RUN_FREQ    = 0x1003;
static constexpr uint16_t REG_RUN_SPEED   = 0x1004;
static constexpr uint16_t REG_OUT_CURRENT = 0x1006;

static constexpr uint16_t REG_F0_00 = 0xF000;
static constexpr uint16_t REG_F0_01 = 0xF001;
static constexpr uint16_t REG_F0_18 = 0xF018;
static constexpr uint16_t REG_F0_20 = 0xF020;

static constexpr uint16_t REG_F1_05 = 0xF105;
static constexpr uint16_t REG_F1_06 = 0xF106;

static constexpr uint16_t REG_F7_00 = 0xF700;
static constexpr uint16_t REG_F7_01 = 0xF701;
static constexpr uint16_t REG_F7_02 = 0xF702;
static constexpr uint16_t REG_F7_03 = 0xF703;

static constexpr uint16_t REG_U0_11 = 0x100B;

void VfdM980Debug::begin() {
  modbus_.begin(cfg_.baud);
}

void VfdM980Debug::apply_modbus_config(const ModbusConfig& cfg) {
  cfg_ = cfg;
  modbus_.begin(cfg_.baud);
}

ModbusConfig VfdM980Debug::modbus_config() const {
  return cfg_;
}

bool VfdM980Debug::read_reg(uint16_t reg, uint16_t* value) {
  if (!value) return false;
  uint16_t tmp = 0;
  if (!modbus_.read_holding_registers(cfg_.slave_id, reg, 1, &tmp, cfg_.timeout_ms)) return false;
  *value = tmp;
  return true;
}

bool VfdM980Debug::read_block(uint16_t reg, uint16_t count, uint16_t* out) {
  return modbus_.read_holding_registers(cfg_.slave_id, reg, count, out, cfg_.timeout_ms);
}

bool VfdM980Debug::write_reg(uint16_t reg, uint16_t value) {
  return modbus_.write_single_register(cfg_.slave_id, reg, value, cfg_.timeout_ms);
}

bool VfdM980Debug::read_runtime_snapshot(RuntimeSnapshot* st) {
  if (!st) return false;

  uint16_t regs[7] = {0};
  if (!modbus_.read_holding_registers(cfg_.slave_id, REG_RUN_STATE, 7, regs, cfg_.timeout_ms)) return false;

  st->valid = true;
  st->run_state = regs[0];
  st->fault_code = regs[1];
  st->actual_freq_x10 = (int16_t)regs[3];
  st->actual_speed_raw = (int16_t)regs[4];
  st->output_current_x10 = regs[6];

  uint16_t di_state = 0;
  if (read_reg(REG_U0_11, &di_state)) {
    st->di_state = di_state;
  }

  return true;
}

bool VfdM980Debug::read_mode_switch_snapshot(ModeSwitchSnapshot* st) {
  if (!st) return false;

  uint16_t value = 0;
  if (!read_reg(REG_F0_00, &value)) return false;
  st->f0_00 = value;
  if (!read_reg(REG_F0_01, &value)) return false;
  st->f0_01 = value;
  if (!read_reg(REG_F0_18, &value)) return false;
  st->f0_18 = value;
  if (!read_reg(REG_F0_20, &value)) return false;
  st->f0_20 = value;
  if (!read_reg(REG_F1_05, &value)) return false;
  st->f1_05 = value;
  if (!read_reg(REG_F1_06, &value)) return false;
  st->f1_06 = value;
  if (!read_reg(REG_U0_11, &value)) return false;
  st->u0_11 = value;

  st->valid = true;
  return true;
}

bool VfdM980Debug::read_modbus_snapshot(ModbusSnapshot* st) {
  if (!st) return false;

  uint16_t value = 0;
  if (!read_reg(REG_F7_00, &value)) return false;
  st->f7_00 = value;
  if (!read_reg(REG_F7_01, &value)) return false;
  st->f7_01 = value;
  if (!read_reg(REG_F7_02, &value)) return false;
  st->f7_02 = value;
  if (!read_reg(REG_F7_03, &value)) return false;
  st->f7_03 = value;

  st->valid = true;
  return true;
}

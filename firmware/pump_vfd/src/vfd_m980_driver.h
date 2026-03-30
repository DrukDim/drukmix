#pragma once
#include <stdint.h>
#include "rs485_modbus.h"

struct VfdStatus {
  bool online = false;
  bool running = false;
  uint16_t fault_code = 0;
  int16_t actual_freq_x10 = 0;
  int16_t actual_speed_raw = 0;
  uint16_t output_current_x10 = 0;
  uint16_t di_state = 0;
};

class VfdM980Driver {
public:
  void begin();
  bool set_run_forward();
  bool set_run_reverse();
  bool set_stop_ramp();
  bool reset_fault();
  bool set_frequency_pct_x100(uint16_t value);
  bool poll_status(VfdStatus* st);

private:
  Rs485Modbus modbus_;
  bool clear_fault_sequence_();

};

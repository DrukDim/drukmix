#pragma once
#include <stdint.h>

struct PumpNodeStatus {
  bool online = false;
  bool running = false;
  bool faulted = false;
  uint16_t fault_code = 0;

  int32_t target_milli_lpm = 0;
  int32_t actual_milli_lpm = 0;
  int32_t max_milli_lpm = 0;

  int32_t cmd_setpoint_raw = 0;
  int32_t actual_freq_x10 = 0;
  int16_t actual_speed_raw = 0;
  uint16_t output_current_x10 = 0;
};

class PumpNodeIface {
public:
  virtual ~PumpNodeIface() = default;

  virtual void begin() = 0;
  virtual void update() = 0;

  virtual bool set_flow(int32_t target_milli_lpm) = 0;
  virtual bool stop() = 0;
  virtual bool reset_fault() = 0;
  virtual bool get_status(PumpNodeStatus* st) = 0;
};

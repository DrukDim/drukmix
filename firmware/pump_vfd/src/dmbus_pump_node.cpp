#include "dmbus_pump_node.h"
#include <Arduino.h>
#include "pump_vfd_config.h"

void PumpVfdNode::begin() {
  Serial.begin(115200);
  delay(100);
  vfd_.begin();
  status_.max_milli_lpm = max_milli_lpm_;
  Serial.println("pump_vfd node bootstrap");
}

void PumpVfdNode::update() {
  uint32_t now = millis();

  if (now - last_status_ms_ >= STATUS_PERIOD_MS) {
    last_status_ms_ = now;

    VfdStatus st{};
    if (vfd_.poll_status(&st)) {
      status_.online = true;
      status_.running = st.running;
      status_.fault_code = st.fault_code;
      status_.faulted = (st.fault_code != 0);
      status_.actual_speed_raw = st.actual_speed_raw;
      status_.hw_setpoint_raw = st.actual_freq_x10;
    } else {
      status_.online = false;
    }

    Serial.print("VFD online=");
    Serial.print(status_.online);
    Serial.print(" running=");
    Serial.print(status_.running);
    Serial.print(" fault=");
    Serial.println(status_.fault_code);
  }

  delay(2);
}

bool PumpVfdNode::set_flow(int32_t target_milli_lpm) {
  target_milli_lpm_ = target_milli_lpm;
  status_.target_milli_lpm = target_milli_lpm;

  if (target_milli_lpm <= 0) {
    return stop();
  }

  int32_t pct_x100 = (target_milli_lpm * 10000L) / max_milli_lpm_;
  if (pct_x100 < 0) pct_x100 = 0;
  if (pct_x100 > 10000) pct_x100 = 10000;

  if (!vfd_.set_frequency_pct_x100((uint16_t)pct_x100)) return false;
  if (!vfd_.set_run_forward()) return false;

  status_.running = true;
  status_.hw_setpoint_raw = pct_x100;
  return true;
}

bool PumpVfdNode::stop() {
  bool ok = vfd_.set_stop_ramp();
  status_.running = false;
  status_.target_milli_lpm = 0;
  return ok;
}

bool PumpVfdNode::reset_fault() {
  bool ok = vfd_.reset_fault();
  if (ok) {
    status_.faulted = false;
    status_.fault_code = 0;
  }
  return ok;
}

bool PumpVfdNode::get_status(PumpNodeStatus* st) {
  if (!st) return false;
  *st = status_;
  return true;
}

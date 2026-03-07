#include "dmbus_pump_node.h"
#include <Arduino.h>
#include "pump_vfd_config.h"
#include "espnow_cmd_proto.h"

void PumpVfdNode::begin() {
  vfd_.begin();
  link_.begin(WIFI_CHANNEL, PUMP_VFD_PROTO);

  status_.online = false;
  status_.running = false;
  status_.faulted = false;
  status_.fault_code = 0;
  status_.target_milli_lpm = 0;
  status_.actual_milli_lpm = 0;
  status_.max_milli_lpm = max_milli_lpm_;
  status_.cmd_setpoint_raw = 0;
  status_.actual_freq_x10 = 0;
  status_.actual_speed_raw = 0;
}

void PumpVfdNode::handle_rx_() {
  auto rx = link_.pop_rx();
  if (!rx.valid) return;

  if (rx.type == NOW_SET_MAXLPM) {
    if (rx.pump_max_milli_lpm >= 1000) {
      max_milli_lpm_ = rx.pump_max_milli_lpm;
      status_.max_milli_lpm = max_milli_lpm_;
    }
    link_.send_ack(rx.seq, status_.running ? 1 : 0, status_.fault_code, PUMP_VFD_PROTO);
    return;
  }

  if (rx.type == NOW_CMD_FLOW) {
    bool ok = true;

    if (rx.flags & 0x02) {
      ok = stop();
    } else {
      ok = set_flow(rx.target_milli_lpm);
    }

    uint16_t err = ok ? status_.fault_code : (uint16_t)1;
    link_.send_ack(rx.seq, status_.running ? 1 : 0, err, PUMP_VFD_PROTO);
    return;
  }
}

void PumpVfdNode::update() {
  handle_rx_();

  uint32_t now = millis();
  if (now - last_status_ms_ >= STATUS_PERIOD_MS) {
    last_status_ms_ = now;

    VfdStatus st{};
    if (vfd_.poll_status(&st)) {
      status_.online = true;
      status_.running = st.running;
      status_.fault_code = st.fault_code;
      status_.faulted = (st.fault_code != 0);
      status_.actual_freq_x10 = st.actual_freq_x10;
      status_.actual_speed_raw = st.actual_speed_raw;
    } else {
      status_.online = false;
    }

    link_.send_status(0, status_.running ? 1 : 0, status_.fault_code, now, PUMP_VFD_PROTO);

    Serial.print("VFD online=");
    Serial.print(status_.online);
    Serial.print(" running=");
    Serial.print(status_.running);
    Serial.print(" fault=");
    Serial.print(status_.fault_code);
    Serial.print(" target=");
    Serial.print(status_.target_milli_lpm);
    Serial.print(" max=");
    Serial.print(status_.max_milli_lpm);
    Serial.print(" cmd_raw=");
    Serial.print(status_.cmd_setpoint_raw);
    Serial.print(" actual_freq_x10=");
    Serial.print(status_.actual_freq_x10);
    Serial.print(" speed_raw=");
    Serial.println(status_.actual_speed_raw);
  }

  delay(2);
}

bool PumpVfdNode::set_flow(int32_t target_milli_lpm) {
  target_milli_lpm_ = target_milli_lpm;
  status_.target_milli_lpm = target_milli_lpm;
  status_.max_milli_lpm = max_milli_lpm_;

  if (target_milli_lpm <= 0) {
    return stop();
  }

  int32_t pct_x100 = (target_milli_lpm * 10000L) / max_milli_lpm_;
  if (pct_x100 < 0) pct_x100 = 0;
  if (pct_x100 > 10000) pct_x100 = 10000;

  status_.cmd_setpoint_raw = pct_x100;

  if (!vfd_.set_frequency_pct_x100((uint16_t)pct_x100)) return false;
  if (!vfd_.set_run_forward()) return false;

  status_.running = true;
  return true;
}

bool PumpVfdNode::stop() {
  bool ok = vfd_.set_stop_ramp();
  status_.running = false;
  status_.target_milli_lpm = 0;
  status_.cmd_setpoint_raw = 0;
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

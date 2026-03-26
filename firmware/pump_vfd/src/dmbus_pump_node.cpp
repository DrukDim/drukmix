#include "dmbus_pump_node.h"
#include <Arduino.h>
#include "pump_vfd_config.h"
#include "drukmix_bus_v1.h"
#include "node_identity.h"

void PumpVfdNode::begin() {
  vfd_.begin();
  link_.begin(PUMP_VFD_PROTO);

  status_.online = false;
  status_.running = false;
  status_.faulted = false;
  status_.fault_code = 0;
  status_.target_milli_lpm = 0;
  status_.actual_milli_lpm = 0;
  status_.max_milli_lpm = max_milli_lpm_;
  status_.cmd_setpoint_raw = 0;
  rev_commanded_ = false;
}

void PumpVfdNode::handle_rx_() {
  auto rx = link_.pop_rx();
  if (!rx.valid) return;

  if (rx.msg_type == dmbus::PUMP_SET_MAX_FLOW) {
    if (rx.pump_max_milli_lpm >= 1000) {
      max_milli_lpm_ = rx.pump_max_milli_lpm;
      status_.max_milli_lpm = max_milli_lpm_;
      link_.send_ack(
          rx.seq,
          dmbus::ACK_OK,
          dmbus::ERR_NONE,
          0,
          PUMP_VFD_PROTO,
          NODE_ID_PUMP_VFD,
          0x0001,
          DEVICE_CLASS_PUMP);
    } else {
      link_.send_ack(
          rx.seq,
          dmbus::ACK_ERROR,
          dmbus::ERR_BAD_PARAM,
          0,
          PUMP_VFD_PROTO,
          NODE_ID_PUMP_VFD,
          0x0001,
          DEVICE_CLASS_PUMP);
    }
    return;
  }

  if (rx.msg_type == dmbus::OP_RESET_FAULT) {
    bool ok = reset_fault();

    link_.send_ack(
        rx.seq,
        ok ? dmbus::ACK_OK : dmbus::ACK_ERROR,
        ok ? dmbus::ERR_NONE : dmbus::ERR_HW_FAILURE,
        ok ? 0 : dmbus::FAULT_DRIVER_INTERNAL,
        PUMP_VFD_PROTO,
        NODE_ID_PUMP_VFD,
        0x0001,
        DEVICE_CLASS_PUMP);
    return;
  }

  if (rx.msg_type == dmbus::PUMP_SET_FLOW) {
    if (is_manual_mode_active_()) {
      link_.send_ack(
          rx.seq,
          dmbus::ACK_ERROR,
          dmbus::ERR_BAD_STATE,
          dmbus::FAULT_PUMP_MANUAL_MODE,
          PUMP_VFD_PROTO,
          NODE_ID_PUMP_VFD,
          0x0001,
          DEVICE_CLASS_PUMP);
      return;
    }

    bool ok = true;

    bool rev = (rx.flags & 0x01) != 0;
    if (rx.target_milli_lpm <= 0) ok = stop();
    else ok = set_flow_direction_(rx.target_milli_lpm, rev);

    link_.send_ack(
        rx.seq,
        ok ? dmbus::ACK_OK : dmbus::ACK_ERROR,
        ok ? dmbus::ERR_NONE : dmbus::ERR_HW_FAILURE,
        ok ? 0 : dmbus::FAULT_DRIVER_INTERNAL,
        PUMP_VFD_PROTO,
        NODE_ID_PUMP_VFD,
        0x0001,
        DEVICE_CLASS_PUMP);
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
      status_.fault_code = st.fault_code;
      status_.faulted = (st.fault_code != 0);
      status_.running = status_.faulted ? false : st.running;
      status_.actual_milli_lpm = 0;
    } else {
      status_.online = false;
      status_.running = false;
      status_.actual_milli_lpm = 0;
    }

    link_.send_status(
        0,
        PUMP_VFD_PROTO,
        NODE_ID_PUMP_VFD,
        0x0001,
        DEVICE_CLASS_PUMP,
        status_.online,
        status_.running,
        status_.fault_code,
        status_.target_milli_lpm,
        status_.max_milli_lpm,
        status_.cmd_setpoint_raw,
        compose_pump_flags_());

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
    Serial.print(" vfd_freq_x10=");
    Serial.print(st.actual_freq_x10);
    Serial.print(" vfd_speed_raw=");
    Serial.print(st.actual_speed_raw);
    Serial.print(" vfd_current_x10=");
    Serial.println(st.output_current_x10);
  }

  delay(2);
}

bool PumpVfdNode::set_flow(int32_t target_milli_lpm) {
  return set_flow_direction_(target_milli_lpm, false);
}

bool PumpVfdNode::set_flow_direction_(int32_t target_milli_lpm, bool rev) {
  target_milli_lpm_ = target_milli_lpm;
  status_.target_milli_lpm = target_milli_lpm;
  status_.max_milli_lpm = max_milli_lpm_;
  rev_commanded_ = rev;

  if (target_milli_lpm <= 0) return stop();

  VfdStatus st{};
  if (vfd_.poll_status(&st)) {
    status_.online = true;
    status_.fault_code = st.fault_code;
    status_.faulted = (st.fault_code != 0);
    status_.running = status_.faulted ? false : st.running;
  } else {
    status_.online = false;
    status_.running = false;
    return false;
  }

  if (status_.faulted) {
    status_.target_milli_lpm = 0;
    status_.cmd_setpoint_raw = 0;
    return false;
  }

  int32_t pct_x100 = (target_milli_lpm * 10000L) / max_milli_lpm_;
  if (pct_x100 < 0) pct_x100 = 0;
  if (pct_x100 > 10000) pct_x100 = 10000;

  status_.cmd_setpoint_raw = pct_x100;

  if (!vfd_.set_frequency_pct_x100((uint16_t)pct_x100)) return false;
  if (rev) {
    if (!vfd_.set_run_reverse()) return false;
  } else {
    if (!vfd_.set_run_forward()) return false;
  }

  status_.running = true;
  return true;
}

bool PumpVfdNode::stop() {
  status_.target_milli_lpm = 0;
  status_.cmd_setpoint_raw = 0;
  rev_commanded_ = false;
  // Zero target is host-controlled semantics. Do not invent a separate local
  // ramp policy in the ESP node: first drive the commanded frequency to zero,
  // then issue the backend stop command.
  bool ok_freq = vfd_.set_frequency_pct_x100(0);
  bool ok_stop = vfd_.set_stop_ramp();

  // Do not force running=false here; let poll_status() report when the VFD
  // has actually decelerated to a stop.
  return ok_freq && ok_stop;
}

bool PumpVfdNode::reset_fault() {
  VfdStatus st{};

  auto dump = [&](const char* /*tag*/) -> bool {
    if (vfd_.poll_status(&st)) {
      status_.online = true;
      status_.fault_code = st.fault_code;
      status_.faulted = (st.fault_code != 0);
      status_.running = status_.faulted ? false : st.running;
      return true;
    }

    status_.online = false;
    status_.running = false;
    return false;
  };

  dump("before");

  bool ok = vfd_.reset_fault();
  dump("after_reset_seq");

  uint32_t t0 = millis();
  while (ok && status_.faulted && (millis() - t0) < 2000) {
    delay(150);
    dump("wait_clear");
  }

  if (!status_.faulted) {
    status_.target_milli_lpm = 0;
    status_.cmd_setpoint_raw = 0;
  }

  return ok && !status_.faulted;
}

bool PumpVfdNode::get_status(PumpNodeStatus* st) {
  if (!st) return false;
  *st = status_;
  return true;
}


bool PumpVfdNode::is_manual_mode_active_() const {
  // TODO: replace with real selector / local-mode input
  return false;
}

uint16_t PumpVfdNode::compose_pump_flags_() const {
  uint16_t flags = 0;

  if (status_.running) flags |= dmbus::PUMP_FLAG_RUNNING;
  if (status_.target_milli_lpm > 0) {
    flags |= rev_commanded_ ? dmbus::PUMP_FLAG_REVERSE : dmbus::PUMP_FLAG_FORWARD;
  }
  if (is_manual_mode_active_()) flags |= dmbus::PUMP_FLAG_MANUAL_MODE;
  else flags |= dmbus::PUMP_FLAG_REMOTE_MODE;
  if (status_.online) flags |= dmbus::PUMP_FLAG_HW_READY;
  if (status_.faulted) flags |= dmbus::PUMP_FLAG_FAULT_LATCHED;

  return flags;
}

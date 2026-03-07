#include "PumpLogic.h"
#include "../hal/OdGpio.h"
#include "../drivers/EspNowProto.h"
#include <WiFi.h>

using namespace DrukMixPump;
using namespace DrukMixPump::Drivers;

void Logic::PumpLogic::begin() {
  Serial.begin(115200);
  delay(100);

  pinMode(Pins::SW_FWD, INPUT_PULLUP);
  pinMode(Pins::DIR_SENSE, INPUT_PULLUP);

  Hal::od_off(Pins::DIR_DRIVE);
  Hal::od_off(Pins::WIPER_DRIVE);
  dir_asserted_ = false;
  dir_external_low_ = false;
  last_rev_ = false;

  tpl_.begin();

  // *** CRITICAL FIX: force TPL to 0 on boot ***
  tpl_.forceWrite(0);
  applied_code_ = 0;

  last_cmd_ms_ = millis();
  last_flags_ = Cfg::FLAG_STOP;
  last_target_ = 0;

  // ESP-NOW link
  link_.begin(Cfg::WIFI_CHANNEL, Cfg::PROTO);

  Serial.print("PUMP MAC: ");
  Serial.println(WiFi.macAddress());
  Serial.println("Pump ready (WIPER by switch, TPL by FLAG_AUTO).");
}

void Logic::PumpLogic::update() {
  uint32_t now = millis();

  // Update error flags from link
  err_flags_base_ = link_.getErrFlags();

  // Keep wiper correct (operator flips switch anytime)
  enforce_wiper_by_switch_();

  // Consume rx cmd (flow)
  auto rx = link_.popRxCmd();
  if (rx.valid) {
    if (rx.type == NOW_CMD_FLOW) {
      last_cmd_seq_ = rx.seq;
      last_cmd_ms_ = now;
      last_flags_ = rx.flags;
      last_target_ = rx.target_milli_lpm;

      apply_from_cmd_(now);

      // Ack after applying
      link_.sendAck(rx.seq, applied_code_, build_status_flags_(now), Cfg::PROTO);
    } else if (rx.type == NOW_SET_MAXLPM) {
      pump_max_milli_lpm_ = max<int32_t>(rx.pump_max_milli_lpm, 1000);
      last_cmd_seq_ = rx.seq;
      last_cmd_ms_ = now;
      link_.sendAck(rx.seq, applied_code_, build_status_flags_(now), Cfg::PROTO);
    }
  }

  // Failsafe: if manual -> stop; if auto but not allowed -> stop
  if (manual_any_()) {
    apply_code_(0);
    set_dir_rev_(false);
    last_rev_ = false;
  } else {
    if (!tpl_allowed_(now)) {
      apply_code_(0);
      set_dir_rev_(false);
      last_rev_ = false;
    }
  }

  // Heartbeat status
  if (now - last_status_ms_ >= Cfg::STATUS_PERIOD_MS) {
    last_status_ms_ = now;
    link_.sendStatus(last_cmd_seq_, applied_code_, build_status_flags_(now), now, Cfg::PROTO);
  }

  delay(2);
}

// ----- low level helpers -----
bool Logic::PumpLogic::sw_fwd_active_() const { return digitalRead(Pins::SW_FWD) == LOW; }
bool Logic::PumpLogic::dir_force_low_() const { return digitalRead(Pins::DIR_SENSE) == LOW; }

bool Logic::PumpLogic::manual_rev_active_() const {
  if (!dir_force_low_()) return false;
  if (!dir_asserted_) return true;
  if (dir_external_low_) return true;
  return false;
}

bool Logic::PumpLogic::manual_any_() const {
  return sw_fwd_active_() || manual_rev_active_();
}

bool Logic::PumpLogic::cmd_fresh_(uint32_t now_ms) const {
  return (now_ms - last_cmd_ms_) <= Cfg::CMD_TIMEOUT_MS;
}

bool Logic::PumpLogic::tpl_allowed_(uint32_t now_ms) const {
  if (!cmd_fresh_(now_ms)) return false;
  if ((last_flags_ & Cfg::FLAG_AUTO) == 0) return false;
  if (last_flags_ & Cfg::FLAG_STOP) return false;
  if (last_target_ < Cfg::PUMP_MIN_MILLI_LPM_DEFAULT) return false;
  return true;
}

void Logic::PumpLogic::set_wiper_tpl_(bool on) {
  if (on) Hal::od_on(Pins::WIPER_DRIVE);
  else Hal::od_off(Pins::WIPER_DRIVE);
}

void Logic::PumpLogic::set_dir_rev_(bool want_rev) {
  if (want_rev) {
    // DIR safety: if already LOW -> external forcing, do not assert
    if (dir_force_low_()) {
      dir_external_low_ = true;
      Hal::od_off(Pins::DIR_DRIVE);
      dir_asserted_ = false;
      return;
    }
    dir_external_low_ = false;
    Hal::od_on(Pins::DIR_DRIVE);
    dir_asserted_ = true;
  } else {
    Hal::od_off(Pins::DIR_DRIVE);
    dir_asserted_ = false;
    dir_external_low_ = false;
  }
}

void Logic::PumpLogic::enforce_wiper_by_switch_() {
  // WIPER policy:
  // - manual => MANUAL (relay released)
  // - not manual => TPL (relapump_max_milli_lpm_
  if (manual_any_()) set_wiper_tpl_(false);
  else set_wiper_tpl_(true);
}

uint8_t Logic::PumpLogic::calc_code_from_target_(int32_t target_milli_lpm) const {
  if (target_milli_lpm < Cfg::PUMP_MIN_MILLI_LPM_DEFAULT) return 0;
  int32_t maxv = max<int32_t>(Cfg::PUMP_MAX_MILLI_LPM_DEFAULT, 1000);
  int32_t code = (int32_t)((int64_t)target_milli_lpm * 255 / maxv);
  if (code < 0) code = 0;
  if (code > 255) code = 255;
  return (uint8_t)code;
}

void Logic::PumpLogic::apply_code_(uint8_t code) {
  // Equivalent to monolith apply_code + tpl_write
  if (applied_code_ != code) {
    applied_code_ = code;
    tpl_.apply(code);
  }
}

void Logic::PumpLogic::apply_from_cmd_(uint32_t now_ms) {
  enforce_wiper_by_switch_();

  if (manual_any_()) {
    apply_code_(0);
    set_dir_rev_(false);
    last_rev_ = false;
    return;
  }

  if (!tpl_allowed_(now_ms)) {
    apply_code_(0);
    set_dir_rev_(false);
    last_rev_ = false;
    return;
  }

  bool want_rev = (last_flags_ & Cfg::FLAG_REV) != 0;

  if (want_rev != last_rev_) {
    apply_code_(0);
    set_dir_rev_(false);
    delay(Cfg::DIR_DEAD_MS);
    set_dir_rev_(want_rev);
    delay(Cfg::DIR_DEAD_MS);
    last_rev_ = (want_rev && dir_asserted_);
  } else {
    set_dir_rev_(want_rev);
    last_rev_ = (want_rev && dir_asserted_);
  }

  if (manual_rev_active_() || sw_fwd_active_()) {
    apply_code_(0);
    return;
  }

  uint8_t code = calc_code_from_target_(last_target_);
  apply_code_(code);
}

uint16_t Logic::PumpLogic::build_status_flags_(uint32_t now_ms) {
  uint16_t ef = err_flags_base_;

  bool mfwd = sw_fwd_active_();
  bool mrev = manual_rev_active_();
  bool aok  = tpl_allowed_(now_ms);

  if (mfwd) ef |= 0x0010;
  if (mrev) ef |= 0x0020;

  if (aok)  ef |= 0x0040;
  if (aok && !mfwd && !mrev) ef |= 0x0080;

  if (dir_asserted_) ef |= 0x0100;
  if (!manual_any_()) ef |= 0x0200; // WIPER_TPL

  return ef;
}
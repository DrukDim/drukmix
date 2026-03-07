#pragma once
#include <cstdint>
#include "../cfg/BuildConfig.h"
#include "../cfg/Pins.h"
#include "../drivers/Tpl0501.h"
#include "../drivers/EspNowLink.h"

namespace DrukMixPump::Logic {

  class PumpLogic {
   public:
    void begin();
    void update();

   private:
    // Drivers
    Drivers::Tpl0501 tpl_{Pins::CS, Pins::SCLK, Pins::MOSI, Cfg::SPI_HZ};
    Drivers::EspNowLink link_;

    // State (same as monolith)
    uint8_t  applied_code_ = 0;
    uint16_t last_cmd_seq_ = 0;
    uint16_t err_flags_base_ = 0;
    uint32_t last_cmd_ms_ = 0;
    uint8_t  last_flags_ = Cfg::FLAG_STOP;
    int32_t  last_target_ = 0;
    int32_t  pump_max_milli_lpm_ = Cfg::PUMP_MAX_MILLI_LPM_DEFAULT;

    bool dir_asserted_ = false;
    bool dir_external_low_ = false;
    bool last_rev_ = false;

    // Timing
    uint32_t last_status_ms_ = 0;

    // Helpers (same semantics)
    void od_on_(int pin);
    void od_off_(int pin);

    bool sw_fwd_active_() const;
    bool dir_force_low_() const;
    bool manual_rev_active_() const;
    bool manual_any_() const;

    bool cmd_fresh_(uint32_t now_ms) const;
    bool tpl_allowed_(uint32_t now_ms) const;

    void set_wiper_tpl_(bool on);
    void set_dir_rev_(bool want_rev);

    void enforce_wiper_by_switch_();
    uint8_t calc_code_from_target_(int32_t target_milli_lpm) const;
    void apply_code_(uint8_t code);

    void apply_from_cmd_(uint32_t now_ms);

    uint16_t build_status_flags_(uint32_t now_ms);
  };

}
#pragma once
#include <stdint.h>
#include "pump_node_iface.h"
#include "vfd_m980_driver.h"
#include "dmbus_pump_link.h"

class PumpVfdNode : public PumpNodeIface {
public:
  void begin() override;
  void update() override;

  bool set_flow(int32_t target_milli_lpm) override;
  bool stop() override;
  bool reset_fault() override;
  bool get_status(PumpNodeStatus* st) override;

private:
  VfdM980Driver vfd_;
  DmBusPumpLink link_;

  uint32_t last_status_ms_ = 0;
  int32_t target_milli_lpm_ = 0;
  int32_t max_milli_lpm_ = 10000;
  bool rev_commanded_ = false;
  PumpNodeStatus status_{};

  bool is_manual_mode_active_() const;
  uint16_t derive_mode_(uint16_t di_state) const;
  uint16_t compose_pump_flags_() const;
  void handle_rx_();
  bool set_flow_direction_(int32_t target_milli_lpm, bool rev);
};

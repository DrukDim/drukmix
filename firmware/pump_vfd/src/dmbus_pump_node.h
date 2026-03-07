#pragma once
#include <stdint.h>
#include "pump_node_iface.h"
#include "vfd_m980_driver.h"
#include "legacy_now_link.h"

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
  LegacyNowLink link_;

  uint32_t last_status_ms_ = 0;
  int32_t target_milli_lpm_ = 0;
  int32_t max_milli_lpm_ = 10000;
  PumpNodeStatus status_{};

  void handle_rx_();
};

#pragma once
#include "pump_node_iface.h"
#include "logic/PumpLogic.h"

class PumpTplNode : public PumpNodeIface {
public:
  void begin() override;
  void update() override;

  bool set_flow(int32_t target_milli_lpm) override;
  bool stop() override;
  bool reset_fault() override;
  bool get_status(PumpNodeStatus* st) override;

private:
  PumpTpl::Logic::PumpLogic logic_;
  PumpNodeStatus status_{};
};

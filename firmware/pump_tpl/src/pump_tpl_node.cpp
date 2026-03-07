#include "pump_tpl_node.h"

void PumpTplNode::begin() {
  logic_.begin();
}

void PumpTplNode::update() {
  logic_.update();
}

bool PumpTplNode::set_flow(int32_t target_milli_lpm) {
  status_.target_milli_lpm = target_milli_lpm;
  return false;
}

bool PumpTplNode::stop() {
  status_.target_milli_lpm = 0;
  return false;
}

bool PumpTplNode::reset_fault() {
  return false;
}

bool PumpTplNode::get_status(PumpNodeStatus* st) {
  if (!st) return false;
  *st = status_;
  return true;
}

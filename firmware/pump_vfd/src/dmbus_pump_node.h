#pragma once
#include <stdint.h>
#include "vfd_m980_driver.h"

class DmBusPumpNodeVfd {
public:
  void begin();
  void update();

private:
  VfdM980Driver vfd_;
  uint32_t last_status_ms_ = 0;
  int32_t target_milli_lpm_ = 0;
};

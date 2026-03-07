#pragma once
#include <cstdint>

namespace DrukMixPump::Drivers {

  enum NowType : uint8_t {
    NOW_CMD_FLOW   = 1,
    NOW_SET_MAXLPM = 2,
    NOW_ACK        = 100,
    NOW_STATUS     = 101
  };

#pragma pack(push, 1)
  struct NowHdr { uint8_t proto; uint8_t type; uint16_t seq; };

  struct NowCmdFlow {
    NowHdr  h;
    int32_t target_milli_lpm;
    uint8_t flags;
    uint16_t crc;
  };

  struct NowSetMaxLpm {
    NowHdr  h;
    int32_t pump_max_milli_lpm;
    uint16_t crc;
  };

  struct NowAck {
    NowHdr  h;
    uint8_t applied_code;
    uint16_t err_flags;
    uint16_t crc;
  };

  struct NowStatus {
    NowHdr  h;
    uint8_t applied_code;
    uint16_t err_flags;
    uint32_t uptime_ms;
    uint16_t crc;
  };
#pragma pack(pop)

}
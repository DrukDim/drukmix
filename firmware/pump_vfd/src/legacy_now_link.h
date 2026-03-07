#pragma once
#include <stdint.h>

struct LegacyRxCmd {
  bool     valid = false;
  uint8_t  type = 0;
  uint16_t seq = 0;
  int32_t  target_milli_lpm = 0;
  uint8_t  flags = 0;
  int32_t  pump_max_milli_lpm = 0;
};

class LegacyNowLink {
public:
  void begin(int wifi_channel, uint8_t proto);
  LegacyRxCmd pop_rx();
  void send_ack(uint16_t seq, uint8_t applied_code, uint16_t err_flags, uint8_t proto);
  void send_status(uint16_t seq, uint8_t applied_code, uint16_t err_flags, uint32_t uptime_ms, uint8_t proto);

private:
  static void on_recv_thunk_(const uint8_t* mac_addr, const uint8_t* data, int len);
  void on_recv_(const uint8_t* mac_addr, const uint8_t* data, int len);
  void ensure_peer_(const uint8_t* mac);

  static LegacyNowLink* self_;

  bool peer_known_ = false;
  uint8_t peer_mac_[6] = {0};
  LegacyRxCmd rx_{};
  uint8_t proto_ = 1;
};

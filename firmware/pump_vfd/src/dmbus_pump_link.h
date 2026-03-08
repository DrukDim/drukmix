#pragma once
#include <stdint.h>

struct PumpRxCmd {
  bool     valid = false;
  uint8_t  msg_type = 0;
  uint16_t seq = 0;
  int32_t  target_milli_lpm = 0;
  uint8_t  flags = 0;
  int32_t  pump_max_milli_lpm = 0;
  uint16_t fault_selector = 0;
};

class DmBusPumpLink {
public:
  void begin(uint8_t proto);
  PumpRxCmd pop_rx();

  void send_ack(
      uint16_t seq,
      uint8_t ack_status,
      uint16_t err_code,
      uint16_t detail,
      uint8_t proto,
      uint16_t src_node,
      uint16_t dst_node,
      uint8_t device_class);

  void send_status(
      uint16_t seq,
      uint8_t proto,
      uint16_t src_node,
      uint16_t dst_node,
      uint8_t device_class,
      bool online,
      bool running,
      uint16_t fault_code,
      int32_t target_milli_lpm,
      int32_t max_milli_lpm,
      int32_t cmd_setpoint_raw,
      uint16_t pump_flags);

private:
  static void on_recv_thunk_(const uint8_t* mac_addr, const uint8_t* data, int len);
  void on_recv_(const uint8_t* mac_addr, const uint8_t* data, int len);
  void ensure_peer_(const uint8_t mac[6]);

  static DmBusPumpLink* self_;

  bool peer_known_ = false;
  uint8_t peer_mac_[6] = {0};
  PumpRxCmd rx_{};
  uint8_t proto_ = 1;
};

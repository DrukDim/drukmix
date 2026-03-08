#pragma once
#include <stddef.h>
#include <stdint.h>
#include "bridge_proto.h"

struct UsbStatusPayload {
  bool     pump_link = false;
  uint16_t last_seen_div10 = 0;
  uint16_t last_ack_seq = 0;
  uint8_t  applied_code = 0;
  uint16_t err_flags = 0;
  uint16_t retry_count = 0;
  uint16_t send_fail_count = 0;
  int32_t  pump_max_milli_lpm = 0;

  uint16_t pump_state = 0;
  uint16_t pump_fault_code = 0;
  bool     pump_online = false;
  bool     pump_running = false;
  int32_t  target_milli_lpm = 0;
  int32_t  actual_milli_lpm = 0;
  int32_t  hw_setpoint_raw = 0;
  uint16_t pump_flags = 0;
};

class UsbLink {
public:
  void begin(int baudrate);
  bool poll_packet(uint8_t* out_decoded, size_t out_cap, size_t* out_len);
  void send_status(uint8_t proto, uint16_t seq_reply, const UsbStatusPayload& st);

  static bool parse_packet(const uint8_t* pkt, size_t len, UsbHdr* hdr, const uint8_t** body, size_t* body_len);

private:
  uint8_t rxbuf_[256] = {0};
  size_t  rxlen_ = 0;
};

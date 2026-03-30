#include "usb_link.h"
#include <Arduino.h>
#include <string.h>
#include "cobs_crc.h"

void UsbLink::begin(int baudrate) {
  Serial.begin(baudrate);
}

bool UsbLink::poll_packet(uint8_t* out_decoded, size_t out_cap, size_t* out_len) {
  while (Serial.available()) {
    uint8_t b = (uint8_t)Serial.read();
    if (b == 0x00) {
      if (rxlen_ > 0) {
        size_t decl = 0;
        bool ok = cobs_decode(rxbuf_, rxlen_, out_decoded, &decl);
        rxlen_ = 0;
        if (!ok) return false;
        if (decl > out_cap) return false;
        *out_len = decl;
        return true;
      }
      rxlen_ = 0;
    } else {
      if (rxlen_ < sizeof(rxbuf_)) rxbuf_[rxlen_++] = b;
      else rxlen_ = 0;
    }
  }
  return false;
}

void UsbLink::send_status(uint8_t proto, uint16_t seq_reply, const UsbStatusPayload& st) {
  uint8_t payload[256];
  size_t off = 0;

  UsbHdr hdr{proto, USB_BRIDGE_STATUS, seq_reply, millis()};
  memcpy(payload + off, &hdr, sizeof(hdr));
  off += sizeof(hdr);

  payload[off++] = st.pump_link ? 1 : 0;
  *(uint16_t*)(payload + off) = st.last_seen_div10; off += 2;
  *(uint16_t*)(payload + off) = st.last_ack_seq; off += 2;
  payload[off++] = st.applied_code;
  *(uint16_t*)(payload + off) = st.err_flags; off += 2;
  *(uint16_t*)(payload + off) = st.retry_count; off += 2;
  *(uint16_t*)(payload + off) = st.send_fail_count; off += 2;
  *(int32_t*)(payload + off) = st.pump_max_milli_lpm; off += 4;

  *(uint16_t*)(payload + off) = st.pump_state; off += 2;
  *(uint16_t*)(payload + off) = st.pump_mode; off += 2;
  *(uint16_t*)(payload + off) = st.pump_fault_code; off += 2;
  payload[off++] = st.pump_online ? 1 : 0;
  payload[off++] = st.pump_running ? 1 : 0;
  *(int32_t*)(payload + off) = st.target_milli_lpm; off += 4;
  *(int32_t*)(payload + off) = st.actual_milli_lpm; off += 4;
  *(int32_t*)(payload + off) = st.hw_setpoint_raw; off += 4;
  *(uint16_t*)(payload + off) = st.pump_flags; off += 2;

  uint16_t crc = crc16_ccitt_false(payload, off);
  *(uint16_t*)(payload + off) = crc; off += 2;

  uint8_t enc[300];
  size_t encl = cobs_encode(payload, off, enc);
  Serial.write(enc, encl);
  Serial.write((uint8_t)0x00);
}

bool UsbLink::parse_packet(const uint8_t* pkt, size_t len, UsbHdr* hdr, const uint8_t** body, size_t* body_len) {
  if (!pkt || !hdr || !body || !body_len) return false;
  if (len < sizeof(UsbHdr) + 2) return false;

  uint16_t got = *(const uint16_t*)(pkt + len - 2);
  uint16_t calc = crc16_ccitt_false(pkt, len - 2);
  if (got != calc) return false;

  memcpy(hdr, pkt, sizeof(UsbHdr));
  *body = pkt + sizeof(UsbHdr);
  *body_len = len - sizeof(UsbHdr) - 2;
  return true;
}

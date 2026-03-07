#pragma once
#include <stdint.h>
#include <stddef.h>
#include "drukmix_bus_v1.h"

namespace dmbus {

static inline uint16_t crc16_ccitt_false(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
  }
  return crc;
}

static inline bool header_basic_valid(const Header& h) {
  if (h.proto_ver != PROTO_VER) return false;
  if (h.payload_len > 240) return false;
  return true;
}

static inline bool frame_valid(const uint8_t* frame, size_t len) {
  if (!frame) return false;
  if (len < sizeof(Header) + sizeof(FrameCrc)) return false;

  const auto* h = reinterpret_cast<const Header*>(frame);
  if (!header_basic_valid(*h)) return false;

  const size_t expected = sizeof(Header) + (size_t)h->payload_len + sizeof(FrameCrc);
  if (len != expected) return false;

  const uint16_t got =
      *(const uint16_t*)(frame + len - sizeof(FrameCrc));
  const uint16_t calc = crc16_ccitt_false(frame, len - sizeof(FrameCrc));
  return got == calc;
}

static inline uint16_t frame_crc(const uint8_t* frame_wo_crc, size_t len_wo_crc) {
  return crc16_ccitt_false(frame_wo_crc, len_wo_crc);
}

} // namespace dmbus

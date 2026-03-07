#include "cobs_crc.h"

uint16_t crc16_ccitt_false(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
  }
  return crc;
}

size_t cobs_encode(const uint8_t* in, size_t len, uint8_t* out) {
  uint8_t* start = out;
  uint8_t* code_ptr = out++;
  uint8_t code = 1;

  for (size_t i = 0; i < len; i++) {
    if (in[i] == 0) {
      *code_ptr = code;
      code_ptr = out++;
      code = 1;
    } else {
      *out++ = in[i];
      code++;
      if (code == 0xFF) {
        *code_ptr = code;
        code_ptr = out++;
        code = 1;
      }
    }
  }

  *code_ptr = code;
  return (size_t)(out - start);
}

bool cobs_decode(const uint8_t* in, size_t len, uint8_t* out, size_t* out_len) {
  const uint8_t* end = in + len;
  uint8_t* o = out;

  while (in < end) {
    uint8_t code = *in++;
    if (code == 0) return false;

    for (uint8_t i = 1; i < code; i++) {
      if (in >= end) return false;
      *o++ = *in++;
    }
    if (code != 0xFF && in < end) *o++ = 0;
  }

  *out_len = (size_t)(o - out);
  return true;
}

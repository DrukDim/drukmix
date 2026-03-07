#pragma once
#include <stddef.h>
#include <stdint.h>

uint16_t crc16_ccitt_false(const uint8_t* data, size_t len);
size_t cobs_encode(const uint8_t* in, size_t len, uint8_t* out);
bool cobs_decode(const uint8_t* in, size_t len, uint8_t* out, size_t* out_len);

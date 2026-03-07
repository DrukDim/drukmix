#pragma once
#include <stdint.h>

class Rs485Modbus {
public:
  void begin();
  bool write_single_register(uint8_t slave, uint16_t reg, uint16_t value);
  bool read_holding_registers(uint8_t slave, uint16_t reg, uint16_t count, uint16_t* out);

private:
  uint16_t crc16_modbus_(const uint8_t* data, uint16_t len);
};

#pragma once
#include <stdint.h>

class Rs485Modbus {
public:
  void begin(uint32_t baud = 9600);

  bool write_single_register(uint8_t slave, uint16_t reg, uint16_t value, uint32_t timeout_ms = 120);
  bool write_single_register_broadcast(uint16_t reg, uint16_t value);
  bool read_holding_registers(uint8_t slave, uint16_t reg, uint16_t count, uint16_t* out, uint32_t timeout_ms = 120);

private:
  uint16_t crc16_modbus_(const uint8_t* data, uint16_t len);

  bool txrx_(
      const uint8_t* tx,
      uint16_t tx_len,
      uint8_t* rx,
      uint16_t rx_cap,
      uint16_t* rx_len,
      uint32_t timeout_ms);

  void set_tx_mode_(bool tx_mode);
};

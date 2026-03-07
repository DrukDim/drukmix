#include "rs485_modbus.h"
#include <Arduino.h>
#include "pump_vfd_config.h"

void Rs485Modbus::begin() {
  Serial2.begin(UART_BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
  pinMode(UART_RTS_PIN, OUTPUT);
  digitalWrite(UART_RTS_PIN, LOW);
}

uint16_t Rs485Modbus::crc16_modbus_(const uint8_t* data, uint16_t len) {
  uint16_t crc = 0xFFFF;
  for (uint16_t pos = 0; pos < len; pos++) {
    crc ^= (uint16_t)data[pos];
    for (int i = 0; i < 8; i++) {
      if (crc & 1) {
        crc >>= 1;
        crc ^= 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }
  return crc;
}

bool Rs485Modbus::write_single_register(uint8_t slave, uint16_t reg, uint16_t value) {
  (void)slave;
  (void)reg;
  (void)value;
  return false;
}

bool Rs485Modbus::read_holding_registers(uint8_t slave, uint16_t reg, uint16_t count, uint16_t* out) {
  (void)slave;
  (void)reg;
  (void)count;
  (void)out;
  return false;
}

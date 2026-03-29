#include "rs485_modbus.h"
#include <Arduino.h>
#include "debug_config.h"

static HardwareSerial& VFD_SERIAL = Serial2;

void Rs485Modbus::begin(uint32_t baud) {
  pinMode(UART_RTS_PIN, OUTPUT);
  set_tx_mode_(false);

  VFD_SERIAL.begin(
      baud,
      SERIAL_8N1,
      UART_RX_PIN,
      UART_TX_PIN);
}

void Rs485Modbus::set_tx_mode_(bool tx_mode) {
  digitalWrite(UART_RTS_PIN, tx_mode ? HIGH : LOW);
}

uint16_t Rs485Modbus::crc16_modbus_(const uint8_t* data, uint16_t len) {
  uint16_t crc = 0xFFFF;
  for (uint16_t pos = 0; pos < len; pos++) {
    crc ^= (uint16_t)data[pos];
    for (int i = 0; i < 8; i++) {
      if (crc & 0x0001) {
        crc >>= 1;
        crc ^= 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }
  return crc;
}

bool Rs485Modbus::txrx_(
    const uint8_t* tx,
    uint16_t tx_len,
    uint8_t* rx,
    uint16_t rx_cap,
    uint16_t* rx_len,
    uint32_t timeout_ms) {

  if (!tx || !rx || !rx_len) return false;

  while (VFD_SERIAL.available()) VFD_SERIAL.read();

  set_tx_mode_(true);
  delayMicroseconds(200);

  size_t written = VFD_SERIAL.write(tx, tx_len);
  VFD_SERIAL.flush();

  set_tx_mode_(false);
  delayMicroseconds(150);

  if (written != tx_len) return false;

  uint32_t start = millis();
  uint16_t n = 0;

  while ((millis() - start) < timeout_ms) {
    while (VFD_SERIAL.available()) {
      if (n >= rx_cap) return false;
      rx[n++] = (uint8_t)VFD_SERIAL.read();
      start = millis();
    }
  }

  *rx_len = n;
  return n > 0;
}

bool Rs485Modbus::write_single_register(uint8_t slave, uint16_t reg, uint16_t value, uint32_t timeout_ms) {
  uint8_t tx[8];
  tx[0] = slave;
  tx[1] = 0x06;
  tx[2] = (uint8_t)(reg >> 8);
  tx[3] = (uint8_t)(reg & 0xFF);
  tx[4] = (uint8_t)(value >> 8);
  tx[5] = (uint8_t)(value & 0xFF);

  uint16_t crc = crc16_modbus_(tx, 6);
  tx[6] = (uint8_t)(crc & 0xFF);
  tx[7] = (uint8_t)(crc >> 8);

  uint8_t rx[16];
  uint16_t rx_len = 0;
  if (!txrx_(tx, sizeof(tx), rx, sizeof(rx), &rx_len, timeout_ms)) return false;
  if (rx_len != 8) return false;

  uint16_t got_crc = (uint16_t)rx[6] | ((uint16_t)rx[7] << 8);
  uint16_t calc_crc = crc16_modbus_(rx, 6);
  if (got_crc != calc_crc) return false;

  if (rx[0] != slave) return false;
  if (rx[1] != 0x06) return false;
  if (rx[2] != tx[2] || rx[3] != tx[3]) return false;
  if (rx[4] != tx[4] || rx[5] != tx[5]) return false;

  return true;
}

bool Rs485Modbus::write_single_register_broadcast(uint16_t reg, uint16_t value) {
  uint8_t tx[8];
  tx[0] = 0;
  tx[1] = 0x06;
  tx[2] = (uint8_t)(reg >> 8);
  tx[3] = (uint8_t)(reg & 0xFF);
  tx[4] = (uint8_t)(value >> 8);
  tx[5] = (uint8_t)(value & 0xFF);

  uint16_t crc = crc16_modbus_(tx, 6);
  tx[6] = (uint8_t)(crc & 0xFF);
  tx[7] = (uint8_t)(crc >> 8);

  while (VFD_SERIAL.available()) VFD_SERIAL.read();

  set_tx_mode_(true);
  delayMicroseconds(200);

  size_t written = VFD_SERIAL.write(tx, sizeof(tx));
  VFD_SERIAL.flush();

  set_tx_mode_(false);
  delayMicroseconds(150);

  if (written != sizeof(tx)) return false;

  delay(30);
  return true;
}

bool Rs485Modbus::read_holding_registers(uint8_t slave, uint16_t reg, uint16_t count, uint16_t* out, uint32_t timeout_ms) {
  if (!out || count == 0 || count > 16) return false;

  uint8_t tx[8];
  tx[0] = slave;
  tx[1] = 0x03;
  tx[2] = (uint8_t)(reg >> 8);
  tx[3] = (uint8_t)(reg & 0xFF);
  tx[4] = (uint8_t)(count >> 8);
  tx[5] = (uint8_t)(count & 0xFF);

  uint16_t crc = crc16_modbus_(tx, 6);
  tx[6] = (uint8_t)(crc & 0xFF);
  tx[7] = (uint8_t)(crc >> 8);

  uint8_t rx[64];
  uint16_t rx_len = 0;
  if (!txrx_(tx, sizeof(tx), rx, sizeof(rx), &rx_len, timeout_ms)) return false;

  uint16_t expected = (uint16_t)(5 + 2 * count);
  if (rx_len != expected) return false;

  uint16_t got_crc = (uint16_t)rx[rx_len - 2] | ((uint16_t)rx[rx_len - 1] << 8);
  uint16_t calc_crc = crc16_modbus_(rx, rx_len - 2);
  if (got_crc != calc_crc) return false;

  if (rx[0] != slave) return false;
  if (rx[1] != 0x03) return false;
  if (rx[2] != 2 * count) return false;

  for (uint16_t i = 0; i < count; i++) {
    out[i] = ((uint16_t)rx[3 + i * 2] << 8) | rx[4 + i * 2];
  }

  return true;
}

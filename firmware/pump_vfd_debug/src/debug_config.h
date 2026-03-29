#pragma once
#include <stdint.h>

static constexpr int DEBUG_SERIAL_BAUD = 115200;

// RS485 / Modbus UART
static constexpr int UART_BAUD = 9600;
static constexpr int UART_RX_PIN = 16;
static constexpr int UART_TX_PIN = 17;
static constexpr int UART_RTS_PIN = 4;

static constexpr uint8_t MODBUS_SLAVE_ID = 1;

static constexpr uint32_t MODBUS_REQ_TIMEOUT_MS = 120;

#pragma once
#include <stdint.h>

static constexpr uint8_t  PUMP_VFD_PROTO = 1;
static constexpr uint16_t PUMP_VFD_NODE_ID = 0x0100;

static constexpr int WIFI_CHANNEL = 6;
static constexpr uint32_t STATUS_PERIOD_MS = 200;
static constexpr uint32_t CMD_TIMEOUT_MS = 800;

// RS485 / Modbus UART
static constexpr int UART_NUM_VFD = 2;
static constexpr int UART_BAUD = 9600;
static constexpr int UART_RX_PIN = 16;
static constexpr int UART_TX_PIN = 17;
static constexpr int UART_RTS_PIN = 4;   // DE/RE if used

static constexpr uint8_t MODBUS_SLAVE_ID = 1;

// Physical AUTO/MANUAL button truth proven on the current M980 integration:
// the DI3 line state is visible in U0-11 as bit 2 (mask 0x0004), and a set bit
// means AUTO is selected while a cleared bit means MANUAL.
static constexpr uint16_t MODE_SWITCH_DI_MASK = 0x0004;
static constexpr bool MODE_SWITCH_MASK_SET_IS_AUTO = true;

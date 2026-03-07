#pragma once
#include <stdint.h>

static constexpr uint8_t  BRIDGE_PROTO = 1;
static constexpr uint16_t BRIDGE_NODE_ID = 0x0001;

static constexpr int      WIFI_CHANNEL = 6;
static constexpr int      SERIAL_BAUD = 921600;

static constexpr uint32_t ACK_TIMEOUT_MS = 120;
static constexpr uint8_t  MAX_RETRY = 3;

static constexpr uint32_t STATUS_PUSH_MS = 200;
static constexpr uint32_t DEVICE_OFFLINE_MS = 1200;

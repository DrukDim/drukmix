#pragma once
#include <stdint.h>

struct PeerEntry {
  uint16_t node_id;
  uint8_t  device_class;
  uint8_t  mac[6];
};

static constexpr uint16_t NODE_ID_BRIDGE    = 0x0001;
static constexpr uint16_t NODE_ID_PUMP_MAIN = 0x0100;

static constexpr uint8_t DEV_CLASS_BRIDGE = 1;
static constexpr uint8_t DEV_CLASS_PUMP   = 2;

const PeerEntry* peer_find_by_node(uint16_t node_id);
const PeerEntry* peer_get_pump_main();

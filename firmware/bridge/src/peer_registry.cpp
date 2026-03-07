#include "peer_registry.h"

static const PeerEntry g_peers[] = {
  { NODE_ID_PUMP_MAIN, DEV_CLASS_PUMP, {0xD4, 0xE9, 0xF4, 0xFA, 0x88, 0x34} },
};

const PeerEntry* peer_find_by_node(uint16_t node_id) {
  for (const auto& p : g_peers) {
    if (p.node_id == node_id) return &p;
  }
  return nullptr;
}

const PeerEntry* peer_get_pump_main() {
  return peer_find_by_node(NODE_ID_PUMP_MAIN);
}

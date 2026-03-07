#include "peer_table.h"
#include <string.h>

PeerRecord* PeerTable::upsert(
    uint16_t node_id,
    uint8_t device_class,
    uint8_t driver_type,
    uint32_t uid_lo,
    uint32_t uid_hi,
    const uint8_t mac[6],
    uint32_t now_ms) {

  for (auto& p : peers_) {
    if (p.used && p.node_id == node_id) {
      p.device_class = device_class;
      p.driver_type = driver_type;
      p.hardware_uid_lo = uid_lo;
      p.hardware_uid_hi = uid_hi;
      memcpy(p.mac, mac, 6);
      p.last_seen_ms = now_ms;
      return &p;
    }
  }

  for (auto& p : peers_) {
    if (!p.used) {
      p.used = true;
      p.node_id = node_id;
      p.device_class = device_class;
      p.driver_type = driver_type;
      p.hardware_uid_lo = uid_lo;
      p.hardware_uid_hi = uid_hi;
      memcpy(p.mac, mac, 6);
      p.last_seen_ms = now_ms;
      return &p;
    }
  }

  return nullptr;
}

PeerRecord* PeerTable::find_by_node(uint16_t node_id) {
  for (auto& p : peers_) {
    if (p.used && p.node_id == node_id) return &p;
  }
  return nullptr;
}

const PeerRecord* PeerTable::find_by_node(uint16_t node_id) const {
  for (const auto& p : peers_) {
    if (p.used && p.node_id == node_id) return &p;
  }
  return nullptr;
}

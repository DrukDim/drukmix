#pragma once
#include <stdint.h>

struct PeerRecord {
  bool     used = false;
  uint16_t node_id = 0;
  uint8_t  device_class = 0;
  uint8_t  driver_type = 0;
  uint32_t hardware_uid_lo = 0;
  uint32_t hardware_uid_hi = 0;
  uint8_t  mac[6] = {0};
  uint32_t last_seen_ms = 0;
};

class PeerTable {
public:
  static constexpr int MAX_PEERS = 8;

  PeerRecord* upsert(
      uint16_t node_id,
      uint8_t device_class,
      uint8_t driver_type,
      uint32_t uid_lo,
      uint32_t uid_hi,
      const uint8_t mac[6],
      uint32_t now_ms);

  PeerRecord* find_by_node(uint16_t node_id);
  const PeerRecord* find_by_node(uint16_t node_id) const;

private:
  PeerRecord peers_[MAX_PEERS]{};
};

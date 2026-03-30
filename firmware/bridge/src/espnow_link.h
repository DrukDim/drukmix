#pragma once
#include <stdint.h>

struct EspNowState {
  uint8_t  last_applied = 0;
  uint16_t last_err = 0;
  uint16_t last_ack_seq = 0;
  uint16_t pending_seq = 0;
  uint32_t last_seen_ms = 0;

  bool     wait_ack = false;
  uint8_t  retry_left = 0;
  uint32_t last_send_ms = 0;

  uint16_t retry_count = 0;
  uint16_t send_fail_count = 0;

  uint16_t pump_state = 0;
  uint16_t pump_mode = 0;
  uint16_t pump_fault_code = 0;
  bool     pump_online = false;
  bool     pump_running = false;
  int32_t  target_milli_lpm = 0;
  int32_t  actual_milli_lpm = 0;
  int32_t  max_milli_lpm = 0;
  int32_t  hw_setpoint_raw = 0;
  uint16_t pump_flags = 0;
};

void espnow_begin(int wifi_channel);
void espnow_add_peer(const uint8_t mac[6]);

void espnow_send_flow(
    const uint8_t mac[6],
    uint16_t dst_node,
    uint8_t proto,
    uint16_t seq,
    int32_t target_milli_lpm,
    uint8_t flags,
    uint32_t now_ms,
    EspNowState* st);

void espnow_send_maxlpm(
    const uint8_t mac[6],
    uint16_t dst_node,
    uint8_t proto,
    uint16_t seq,
    int32_t pump_max_milli_lpm,
    uint32_t now_ms,
    EspNowState* st);

void espnow_send_reset_fault(
    const uint8_t mac[6],
    uint16_t dst_node,
    uint8_t proto,
    uint16_t seq,
    uint16_t selector,
    uint32_t now_ms,
    EspNowState* st);

void espnow_on_recv(
    const uint8_t* mac_addr,
    const uint8_t* data,
    int len,
    const uint8_t expected_mac[6],
    uint16_t expected_node,
    uint8_t proto,
    EspNowState* st);

#include "espnow_link.h"
#include <string.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "drukmix_bus_v1.h"
#include "drukmix_bus_util.h"

static constexpr uint16_t BRIDGE_NODE_ID = 0x0001;
static constexpr uint16_t PUMP_NODE_ID   = 0x0100;
static constexpr uint8_t  DEVICE_CLASS_BRIDGE = dmbus::DEV_BRIDGE;

void espnow_begin(int wifi_channel) {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_channel(wifi_channel, WIFI_SECOND_CHAN_NONE);
}

void espnow_add_peer(const uint8_t mac[6]) {
  if (!mac) return;
  if (esp_now_is_peer_exist(mac)) return;

  esp_now_peer_info_t p{};
  memcpy(p.peer_addr, mac, 6);
  p.channel = 0;
  p.encrypt = false;
  p.ifidx = WIFI_IF_STA;
  esp_now_add_peer(&p);
}

namespace {
#pragma pack(push, 1)

struct FramePumpSetFlow {
  dmbus::Header h;
  dmbus::PumpSetFlow p;
  dmbus::FrameCrc crc;
};

struct FramePumpSetMax {
  dmbus::Header h;
  dmbus::PumpSetMaxFlow p;
  dmbus::FrameCrc crc;
};

struct FrameResetFault {
  dmbus::Header h;
  dmbus::ResetFault p;
  dmbus::FrameCrc crc;
};

struct FrameAck {
  dmbus::Header h;
  dmbus::Ack p;
  dmbus::FrameCrc crc;
};

struct FramePumpStatus {
  dmbus::Header h;
  dmbus::PumpStatus p;
  dmbus::FrameCrc crc;
};

#pragma pack(pop)
}

void espnow_send_flow(
    const uint8_t mac[6],
    uint8_t proto,
    uint16_t seq,
    int32_t target_milli_lpm,
    uint8_t flags,
    uint32_t now_ms,
    EspNowState* st) {

  FramePumpSetFlow f{};
  f.h.proto_ver = proto;
  f.h.msg_type = dmbus::MSG_CMD;
  f.h.seq = seq;
  f.h.src_node = BRIDGE_NODE_ID;
  f.h.dst_node = PUMP_NODE_ID;
  f.h.device_class = DEVICE_CLASS_BRIDGE;
  f.h.opcode = dmbus::PUMP_SET_FLOW;
  f.h.payload_len = sizeof(dmbus::PumpSetFlow);

  f.p.target_milli_lpm = target_milli_lpm;
  f.p.flags = flags;
  f.p.reserved[0] = 0;
  f.p.reserved[1] = 0;
  f.p.reserved[2] = 0;

  f.crc.crc16 = dmbus::frame_crc((const uint8_t*)&f, sizeof(f) - sizeof(f.crc));

  esp_err_t r = esp_now_send(mac, (const uint8_t*)&f, sizeof(f));
  if (st) {
    if (r != ESP_OK) st->send_fail_count++;
    st->last_send_ms = now_ms;
  }
}

void espnow_send_maxlpm(
    const uint8_t mac[6],
    uint8_t proto,
    uint16_t seq,
    int32_t pump_max_milli_lpm,
    uint32_t now_ms,
    EspNowState* st) {

  FramePumpSetMax f{};
  f.h.proto_ver = proto;
  f.h.msg_type = dmbus::MSG_CMD;
  f.h.seq = seq;
  f.h.src_node = BRIDGE_NODE_ID;
  f.h.dst_node = PUMP_NODE_ID;
  f.h.device_class = DEVICE_CLASS_BRIDGE;
  f.h.opcode = dmbus::PUMP_SET_MAX_FLOW;
  f.h.payload_len = sizeof(dmbus::PumpSetMaxFlow);

  f.p.max_milli_lpm = pump_max_milli_lpm;
  f.crc.crc16 = dmbus::frame_crc((const uint8_t*)&f, sizeof(f) - sizeof(f.crc));

  esp_err_t r = esp_now_send(mac, (const uint8_t*)&f, sizeof(f));
  if (st) {
    if (r != ESP_OK) st->send_fail_count++;
    st->last_send_ms = now_ms;
  }
}


void espnow_send_reset_fault(
    const uint8_t mac[6],
    uint8_t proto,
    uint16_t seq,
    uint16_t selector,
    uint32_t now_ms,
    EspNowState* st) {

  FrameResetFault f{};
  f.h.proto_ver = proto;
  f.h.msg_type = dmbus::MSG_CMD;
  f.h.seq = seq;
  f.h.src_node = BRIDGE_NODE_ID;
  f.h.dst_node = PUMP_NODE_ID;
  f.h.device_class = DEVICE_CLASS_BRIDGE;
  f.h.opcode = dmbus::OP_RESET_FAULT;
  f.h.payload_len = sizeof(dmbus::ResetFault);

  f.p.fault_selector = selector;
  f.crc.crc16 = dmbus::frame_crc((const uint8_t*)&f, sizeof(f) - sizeof(f.crc));

  esp_err_t r = esp_now_send(mac, (const uint8_t*)&f, sizeof(f));
  if (st) {
    if (r != ESP_OK) st->send_fail_count++;
    st->last_send_ms = now_ms;
  }
}

void espnow_on_recv(
    const uint8_t* mac_addr,
    const uint8_t* data,
    int len,
    uint8_t proto,
    EspNowState* st) {

  (void)mac_addr;

  if (!data || !st) return;
  if (len < (int)(sizeof(dmbus::Header) + sizeof(dmbus::FrameCrc))) return;
  if (!dmbus::frame_valid(data, (size_t)len)) return;

  const auto* h = reinterpret_cast<const dmbus::Header*>(data);
  if (h->proto_ver != proto) return;
  if (h->dst_node != BRIDGE_NODE_ID && h->dst_node != dmbus::NODE_BROADCAST) return;

  st->last_seen_ms = millis();

  if (h->msg_type == dmbus::MSG_ACK &&
      len == (int)sizeof(FrameAck) &&
      h->payload_len == sizeof(dmbus::Ack)) {

    const auto* a = reinterpret_cast<const FrameAck*>(data);
    st->last_ack_seq = a->p.ack_seq;

    if (st->wait_ack && a->p.ack_seq == st->pending_seq) {
      st->last_applied = (a->p.status == dmbus::ACK_OK) ? 1 : 0;
      st->last_err = a->p.detail ? a->p.detail : a->p.err_code;
      st->wait_ack = false;
      st->pending_seq = 0;
    }
    return;
  }

  if (h->msg_type == dmbus::MSG_STATUS &&
      len == (int)sizeof(FramePumpStatus) &&
      h->payload_len == sizeof(dmbus::PumpStatus)) {

    const auto* s = reinterpret_cast<const FramePumpStatus*>(data);

    st->pump_state = s->p.c.state;
    st->pump_fault_code = s->p.c.fault_code;
    st->pump_online = (s->p.c.online != 0);
    st->pump_running = (s->p.pump_flags & dmbus::PUMP_FLAG_RUNNING) != 0;

    st->target_milli_lpm = s->p.target_milli_lpm;
    st->actual_milli_lpm = s->p.actual_milli_lpm;
    st->max_milli_lpm = s->p.max_milli_lpm;
    st->hw_setpoint_raw = s->p.hw_setpoint_raw;
    st->pump_flags = s->p.pump_flags;

    return;
  }
}

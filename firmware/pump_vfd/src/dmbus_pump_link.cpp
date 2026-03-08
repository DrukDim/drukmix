#include "dmbus_pump_link.h"
#include <string.h>
#include <WiFi.h>
#include <esp_now.h>
#include "drukmix_bus_v1.h"
#include "drukmix_bus_util.h"
#include "node_identity.h"

DmBusPumpLink* DmBusPumpLink::self_ = nullptr;

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

void DmBusPumpLink::begin(uint8_t proto) {
  proto_ = proto;
  self_ = this;
  esp_now_register_recv_cb(on_recv_thunk_);
}

PumpRxCmd DmBusPumpLink::pop_rx() {
  PumpRxCmd out = rx_;
  rx_ = {};
  return out;
}

void DmBusPumpLink::ensure_peer_(const uint8_t mac[6]) {
  if (!mac) return;

  if (!peer_known_ || memcmp(peer_mac_, mac, 6) != 0) {
    memcpy(peer_mac_, mac, 6);
    peer_known_ = true;
  }

  if (!esp_now_is_peer_exist(peer_mac_)) {
    esp_now_peer_info_t p{};
    memcpy(p.peer_addr, peer_mac_, 6);
    p.channel = 0;
    p.encrypt = false;
    p.ifidx = WIFI_IF_STA;
    esp_now_add_peer(&p);
  }
}

void DmBusPumpLink::on_recv_thunk_(const uint8_t* mac_addr, const uint8_t* data, int len) {
  if (self_) self_->on_recv_(mac_addr, data, len);
}

void DmBusPumpLink::on_recv_(const uint8_t* mac_addr, const uint8_t* data, int len) {
  if (!mac_addr || !data) return;
  if (len < (int)(sizeof(dmbus::Header) + sizeof(dmbus::FrameCrc))) return;
  if (!dmbus::frame_valid(data, (size_t)len)) return;

  const auto* h = reinterpret_cast<const dmbus::Header*>(data);
  if (h->proto_ver != proto_) return;
  if (h->dst_node != NODE_ID_PUMP_VFD && h->dst_node != dmbus::NODE_BROADCAST) return;
  if (h->msg_type != dmbus::MSG_CMD) return;

  ensure_peer_(mac_addr);

  if (h->opcode == dmbus::PUMP_SET_FLOW &&
      h->payload_len == sizeof(dmbus::PumpSetFlow) &&
      len == (int)sizeof(FramePumpSetFlow)) {

    const auto* f = reinterpret_cast<const FramePumpSetFlow*>(data);
    rx_.valid = true;
    rx_.msg_type = h->opcode;
    rx_.seq = h->seq;
    rx_.target_milli_lpm = f->p.target_milli_lpm;
    rx_.flags = f->p.flags;
    return;
  }

  if (h->opcode == dmbus::PUMP_SET_MAX_FLOW &&
      h->payload_len == sizeof(dmbus::PumpSetMaxFlow) &&
      len == (int)sizeof(FramePumpSetMax)) {

    const auto* f = reinterpret_cast<const FramePumpSetMax*>(data);
    rx_.valid = true;
    rx_.msg_type = h->opcode;
    rx_.seq = h->seq;
    rx_.pump_max_milli_lpm = f->p.max_milli_lpm;
    return;
  }

  if (h->opcode == dmbus::OP_RESET_FAULT &&
      h->payload_len == sizeof(dmbus::ResetFault) &&
      len == (int)sizeof(FrameResetFault)) {

    const auto* f = reinterpret_cast<const FrameResetFault*>(data);
    Serial.print("[RX] OP_RESET_FAULT seq=");
    Serial.print(h->seq);
    Serial.print(" selector=");
    Serial.println(f->p.fault_selector);

    rx_.valid = true;
    rx_.msg_type = h->opcode;
    rx_.seq = h->seq;
    rx_.fault_selector = f->p.fault_selector;
    return;
  }
}

void DmBusPumpLink::send_ack(
    uint16_t seq,
    uint8_t ack_status,
    uint16_t err_code,
    uint16_t detail,
    uint8_t proto,
    uint16_t src_node,
    uint16_t dst_node,
    uint8_t device_class) {

  if (!peer_known_) return;

  FrameAck f{};
  f.h.proto_ver = proto;
  f.h.msg_type = dmbus::MSG_ACK;
  f.h.seq = seq;
  f.h.src_node = src_node;
  f.h.dst_node = dst_node;
  f.h.device_class = device_class;
  f.h.opcode = 0;
  f.h.payload_len = sizeof(dmbus::Ack);

  f.p.ack_seq = seq;
  f.p.status = ack_status;
  f.p.reserved = 0;
  f.p.err_code = err_code;
  f.p.detail = detail;

  f.crc.crc16 = dmbus::frame_crc((const uint8_t*)&f, sizeof(f) - sizeof(f.crc));
  esp_now_send(peer_mac_, (const uint8_t*)&f, sizeof(f));
}

void DmBusPumpLink::send_status(
    uint16_t seq,
    uint8_t proto,
    uint16_t src_node,
    uint16_t dst_node,
    uint8_t device_class,
    bool running,
    uint16_t fault_code,
    int32_t target_milli_lpm,
    int32_t max_milli_lpm,
    int32_t cmd_setpoint_raw,
    uint16_t pump_flags) {

  if (!peer_known_) return;

  FramePumpStatus f{};
  f.h.proto_ver = proto;
  f.h.msg_type = dmbus::MSG_STATUS;
  f.h.seq = seq;
  f.h.src_node = src_node;
  f.h.dst_node = dst_node;
  f.h.device_class = device_class;
  f.h.opcode = 0;
  f.h.payload_len = sizeof(dmbus::PumpStatus);

  f.p.c.uptime_ms = millis();
  f.p.c.state = fault_code ? dmbus::STATE_FAULT : (running ? dmbus::STATE_RUNNING : dmbus::STATE_READY);
  f.p.c.mode = dmbus::MODE_REMOTE;
  f.p.c.warn_flags = 0;
  f.p.c.fault_code = fault_code;
  f.p.c.online = 1;
  f.p.c.reserved = 0;

  f.p.target_milli_lpm = target_milli_lpm;
  f.p.actual_milli_lpm = 0;
  f.p.max_milli_lpm = max_milli_lpm;
  f.p.hw_setpoint_raw = cmd_setpoint_raw;
  f.p.link_flags = 0;
  f.p.pump_flags = pump_flags;

  f.crc.crc16 = dmbus::frame_crc((const uint8_t*)&f, sizeof(f) - sizeof(f.crc));
  esp_now_send(peer_mac_, (const uint8_t*)&f, sizeof(f));
}

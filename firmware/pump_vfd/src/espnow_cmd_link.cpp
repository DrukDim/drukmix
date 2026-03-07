#include "espnow_cmd_link.h"
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "espnow_cmd_proto.h"
#include "drukmix_bus_util.h"

EspNowCmdLink* EspNowCmdLink::self_ = nullptr;

void EspNowCmdLink::begin(int wifi_channel, uint8_t proto) {
  proto_ = proto;
  self_ = this;

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_channel(wifi_channel, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() != ESP_OK) {
    return;
  }
  esp_now_register_recv_cb(&EspNowCmdLink::on_recv_thunk_);
}

EspNowCmd EspNowCmdLink::pop_rx() {
  EspNowCmd out = rx_;
  rx_.valid = false;
  return out;
}

void EspNowCmdLink::ensure_peer_(const uint8_t* mac) {
  if (peer_known_ && memcmp(mac, peer_mac_, 6) == 0) return;

  memcpy(peer_mac_, mac, 6);
  peer_known_ = true;

  if (!esp_now_is_peer_exist(peer_mac_)) {
    esp_now_peer_info_t p{};
    memcpy(p.peer_addr, peer_mac_, 6);
    p.channel = 0;
    p.encrypt = false;
    p.ifidx = WIFI_IF_STA;
    esp_now_add_peer(&p);
  }
}

void EspNowCmdLink::on_recv_thunk_(const uint8_t* mac_addr, const uint8_t* data, int len) {
  if (self_) self_->on_recv_(mac_addr, data, len);
}

void EspNowCmdLink::on_recv_(const uint8_t* mac_addr, const uint8_t* data, int len) {
  if (!mac_addr || !data) return;
  if (len < (int)sizeof(NowHdr) + 2) return;

  const auto* h = reinterpret_cast<const NowHdr*>(data);
  if (h->proto != proto_) return;

  uint16_t got = *(const uint16_t*)(data + len - 2);
  uint16_t calc = dmbus::crc16_ccitt_false(data, (size_t)len - 2);
  if (got != calc) return;

  ensure_peer_(mac_addr);

  if (h->type == NOW_CMD_FLOW && len == (int)sizeof(NowCmdFlow)) {
    const auto* c = reinterpret_cast<const NowCmdFlow*>(data);
    rx_.valid = true;
    rx_.type = h->type;
    rx_.seq = c->h.seq;
    rx_.target_milli_lpm = c->target_milli_lpm;
    rx_.flags = c->flags;
  } else if (h->type == NOW_SET_MAXLPM && len == (int)sizeof(NowSetMaxLpm)) {
    const auto* m = reinterpret_cast<const NowSetMaxLpm*>(data);
    rx_.valid = true;
    rx_.type = h->type;
    rx_.seq = m->h.seq;
    rx_.pump_max_milli_lpm = m->pump_max_milli_lpm;
  }
}

void EspNowCmdLink::send_ack(uint16_t seq, uint8_t applied_code, uint16_t err_flags, uint8_t proto) {
  if (!peer_known_) return;

  NowAck pkt{};
  pkt.h = {proto, NOW_ACK, seq};
  pkt.applied_code = applied_code;
  pkt.err_flags = err_flags;
  pkt.crc = dmbus::crc16_ccitt_false((const uint8_t*)&pkt, sizeof(pkt) - 2);
  esp_now_send(peer_mac_, (const uint8_t*)&pkt, sizeof(pkt));
}

void EspNowCmdLink::send_status(uint16_t seq, uint8_t applied_code, uint16_t err_flags, uint32_t uptime_ms, uint8_t proto) {
  if (!peer_known_) return;

  NowStatus pkt{};
  pkt.h = {proto, NOW_STATUS, seq};
  pkt.applied_code = applied_code;
  pkt.err_flags = err_flags;
  pkt.uptime_ms = uptime_ms;
  pkt.crc = dmbus::crc16_ccitt_false((const uint8_t*)&pkt, sizeof(pkt) - 2);
  esp_now_send(peer_mac_, (const uint8_t*)&pkt, sizeof(pkt));
}

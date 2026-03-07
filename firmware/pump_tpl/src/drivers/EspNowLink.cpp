#include "EspNowLink.h"
#include "EspNowProto.h"
#include "../hal/Crc16.h"
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_now.h>

using namespace PumpTpl;

Drivers::EspNowLink* Drivers::EspNowLink::self_ = nullptr;

void Drivers::EspNowLink::begin(int wifi_channel, uint8_t proto) {
  proto_ = proto;
  self_ = this;

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_channel(wifi_channel, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() != ESP_OK) {
    // hard fail: keep running but no link
    Serial.println("ESP-NOW init failed");
    return;
  }
  esp_now_register_recv_cb(&EspNowLink::onRecvThunk_);
}

Drivers::RxCmd Drivers::EspNowLink::popRxCmd() {
  RxCmd out = rx_;
  rx_.valid = false;
  return out;
}

void Drivers::EspNowLink::ensurePeer_(const uint8_t* mac) {
  if (peer_known_ && memcmp(mac, peer_mac_, 6) == 0) return;
  memcpy(peer_mac_, mac, 6);
  peer_known_ = true;

  if (!esp_now_is_peer_exist(peer_mac_)) {
    esp_now_peer_info_t p{};
    memcpy(p.peer_addr, peer_mac_, 6);
    p.channel = 0;           // already locked by esp_wifi_set_channel
    p.encrypt = false;
    p.ifidx = WIFI_IF_STA;
    esp_err_t r = esp_now_add_peer(&p);
    if (r != ESP_OK) err_flags_ |= 0x0001;
  }
}

void Drivers::EspNowLink::onRecvThunk_(const uint8_t* mac_addr, const uint8_t* data, int data_len) {
  if (self_) self_->onRecv_(mac_addr, data, data_len);
}

void Drivers::EspNowLink::onRecv_(const uint8_t* mac_addr, const uint8_t* data, int data_len) {
  if (!mac_addr || !data) return;
  if (data_len < (int)sizeof(NowHdr) + 2) return;

  const NowHdr* h = (const NowHdr*)data;
  if (h->proto != proto_) return;

  uint16_t got = *(const uint16_t*)(data + data_len - 2);
  uint16_t calc = Hal::crc16_ccitt_false(data, (size_t)data_len - 2);
  if (got != calc) { err_flags_ |= 0x0002; return; }

  ensurePeer_(mac_addr);

  if (h->type == NOW_CMD_FLOW && data_len == (int)sizeof(NowCmdFlow)) {
    const NowCmdFlow* c = (const NowCmdFlow*)data;
    rx_.valid = true;
    rx_.type = h->type;
    rx_.seq = c->h.seq;
    rx_.target_milli_lpm = c->target_milli_lpm;
    rx_.flags = c->flags;
  } else if (h->type == NOW_SET_MAXLPM && data_len == (int)sizeof(NowSetMaxLpm)) {
    const NowSetMaxLpm* m = (const NowSetMaxLpm*)data;
    rx_.valid = true;
    rx_.type = h->type;
    rx_.seq = m->h.seq;
    rx_.pump_max_milli_lpm = m->pump_max_milli_lpm;
  } else {
    err_flags_ |= 0x0004;
  }
}

void Drivers::EspNowLink::sendAck(uint16_t seq, uint8_t applied_code, uint16_t err_flags, uint8_t proto) {
  if (!peer_known_) return;
  NowAck pkt{};
  pkt.h = {proto, NOW_ACK, seq};
  pkt.applied_code = applied_code;
  pkt.err_flags = err_flags;
  pkt.crc = Hal::crc16_ccitt_false((uint8_t*)&pkt, sizeof(pkt) - 2);
  esp_now_send(peer_mac_, (uint8_t*)&pkt, sizeof(pkt));
}

void Drivers::EspNowLink::sendStatus(uint16_t last_cmd_seq, uint8_t applied_code, uint16_t err_flags, uint32_t uptime_ms, uint8_t proto) {
  if (!peer_known_) return;
  NowStatus pkt{};
  pkt.h = {proto, NOW_STATUS, last_cmd_seq};
  pkt.applied_code = applied_code;
  pkt.err_flags = err_flags;
  pkt.uptime_ms = uptime_ms;
  pkt.crc = Hal::crc16_ccitt_false((uint8_t*)&pkt, sizeof(pkt) - 2);
  esp_now_send(peer_mac_, (uint8_t*)&pkt, sizeof(pkt));
}
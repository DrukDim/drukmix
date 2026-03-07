#include "espnow_link.h"
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <string.h>
#include "bridge_proto.h"
#include "cobs_crc.h"

void espnow_begin(int wifi_channel) {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_channel(wifi_channel, WIFI_SECOND_CHAN_NONE);
}

void espnow_add_peer(const uint8_t mac[6]) {
  if (esp_now_is_peer_exist(mac)) return;

  esp_now_peer_info_t p{};
  memcpy(p.peer_addr, mac, 6);
  p.channel = 0;
  p.encrypt = false;
  p.ifidx = WIFI_IF_STA;
  esp_now_add_peer(&p);
}

void espnow_send_flow(
    const uint8_t mac[6],
    uint8_t proto,
    uint16_t seq,
    int32_t target_milli_lpm,
    uint8_t flags,
    uint32_t now_ms,
    EspNowState* st) {

  NowCmdFlow pkt{};
  pkt.h = {proto, NOW_CMD_FLOW, seq};
  pkt.target_milli_lpm = target_milli_lpm;
  pkt.flags = flags;
  pkt.crc = crc16_ccitt_false((const uint8_t*)&pkt, sizeof(pkt) - 2);

  esp_err_t r = esp_now_send(mac, (const uint8_t*)&pkt, sizeof(pkt));
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

  NowSetMaxLpm pkt{};
  pkt.h = {proto, NOW_SET_MAXLPM, seq};
  pkt.pump_max_milli_lpm = pump_max_milli_lpm;
  pkt.crc = crc16_ccitt_false((const uint8_t*)&pkt, sizeof(pkt) - 2);

  esp_err_t r = esp_now_send(mac, (const uint8_t*)&pkt, sizeof(pkt));
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

  if (!mac_addr || !data || !st) return;
  if (len < (int)sizeof(NowHdr) + 2) return;

  const NowHdr* h = reinterpret_cast<const NowHdr*>(data);
  if (h->proto != proto) return;

  uint16_t got = *(const uint16_t*)(data + len - 2);
  uint16_t calc = crc16_ccitt_false(data, (size_t)len - 2);
  if (got != calc) return;

  st->last_seen_ms = millis();

  if (h->type == NOW_ACK && len == (int)sizeof(NowAck)) {
    const NowAck* a = reinterpret_cast<const NowAck*>(data);
    st->last_ack_seq = a->h.seq;
    st->last_applied = a->applied_code;
    st->last_err = a->err_flags;
    st->wait_ack = false;
    return;
  }

  if (h->type == NOW_STATUS && len == (int)sizeof(NowStatus)) {
    const NowStatus* s = reinterpret_cast<const NowStatus*>(data);
    st->last_applied = s->applied_code;
    st->last_err = s->err_flags;
    return;
  }
}

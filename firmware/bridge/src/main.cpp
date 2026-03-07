#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include "bridge_config.h"
#include "bridge_proto.h"
#include "cobs_crc.h"
#include "espnow_link.h"
#include "peer_registry.h"
#include "usb_link.h"

static EspNowState g_now_state{};
static const PeerEntry* g_pump_peer = nullptr;

static uint16_t g_cmd_seq = 0;
static int32_t  g_target_milli_lpm = 0;
static uint8_t  g_flags = 0;
static int32_t  g_pump_max_milli_lpm = 10000;

static UsbLink g_usb;

static void on_now_recv(const uint8_t* mac_addr, const uint8_t* data, int len) {
  espnow_on_recv(mac_addr, data, len, BRIDGE_PROTO, &g_now_state);
}

static void usb_send_status(uint16_t seq_reply) {
  uint32_t age_ms = (g_now_state.last_seen_ms == 0) ? 0xFFFFFFFFu : (millis() - g_now_state.last_seen_ms);
  UsbStatusPayload st{};
  st.pump_link = (age_ms < DEVICE_OFFLINE_MS);
  st.last_seen_div10 = (age_ms == 0xFFFFFFFFu) ? 65535 : (uint16_t)min<uint32_t>(age_ms / 10, 65535);
  st.last_ack_seq = g_now_state.last_ack_seq;
  st.applied_code = g_now_state.last_applied;
  st.err_flags = g_now_state.last_err;
  st.retry_count = g_now_state.retry_count;
  st.send_fail_count = g_now_state.send_fail_count;
  st.pump_max_milli_lpm = g_pump_max_milli_lpm;
  g_usb.send_status(BRIDGE_PROTO, seq_reply, st);
}

static void handle_usb_packet(const uint8_t* pkt, size_t len) {
  UsbHdr hdr{};
  const uint8_t* body = nullptr;
  size_t body_len = 0;

  if (!UsbLink::parse_packet(pkt, len, &hdr, &body, &body_len)) return;
  if (hdr.proto != BRIDGE_PROTO) return;

  const UsbHdr* h = &hdr;

  if (h->type == USB_SET_FLOW) {
    if (body_len < 5) return;
    g_target_milli_lpm = *(const int32_t*)body;
    g_flags = *(const uint8_t*)(body + 4);

    g_cmd_seq++;
    g_now_state.retry_left = MAX_RETRY;
    g_now_state.wait_ack = true;
    espnow_send_flow(g_pump_peer->mac, BRIDGE_PROTO, g_cmd_seq, g_target_milli_lpm, g_flags, millis(), &g_now_state);
    usb_send_status(h->seq);

  } else if (h->type == USB_SET_MAXLPM) {
    if (body_len < 4) return;
    g_pump_max_milli_lpm = *(const int32_t*)body;
    espnow_send_maxlpm(g_pump_peer->mac, BRIDGE_PROTO, ++g_cmd_seq, g_pump_max_milli_lpm, millis(), &g_now_state);
    usb_send_status(h->seq);

  } else if (h->type == USB_PING) {
    usb_send_status(h->seq);
  }
}

void setup() {
  g_usb.begin(SERIAL_BAUD);
  delay(50);

  g_pump_peer = peer_get_pump_main();
  if (!g_pump_peer) {
    Serial.println("Pump peer missing");
    while (true) delay(1000);
  }

  espnow_begin(WIFI_CHANNEL);

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed");
    while (true) delay(1000);
  }

  esp_now_register_recv_cb(on_now_recv);
  espnow_add_peer(g_pump_peer->mac);

  Serial.print("BRIDGE MAC: ");
  Serial.println(WiFi.macAddress());
  Serial.println("DrukMix bridge ready");
}

void loop() {
  uint8_t pkt[256];
  size_t pkt_len = 0;
  if (g_usb.poll_packet(pkt, sizeof(pkt), &pkt_len)) {
    handle_usb_packet(pkt, pkt_len);
  }

  if (g_now_state.wait_ack && g_now_state.retry_left > 0 && (millis() - g_now_state.last_send_ms) > ACK_TIMEOUT_MS) {
    g_now_state.retry_left--;
    g_now_state.retry_count++;
    espnow_send_flow(g_pump_peer->mac, BRIDGE_PROTO, g_cmd_seq, g_target_milli_lpm, g_flags, millis(), &g_now_state);
  }

  if (g_now_state.wait_ack && g_now_state.retry_left == 0 && (millis() - g_now_state.last_send_ms) > ACK_TIMEOUT_MS) {
    g_now_state.wait_ack = false;
  }

  static uint32_t last = 0;
  if (millis() - last >= STATUS_PUSH_MS) {
    last = millis();
    usb_send_status(0);
  }

  delay(1);
}

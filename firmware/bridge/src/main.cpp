#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "cobs_crc.h"
#include "bridge_proto.h"
#include "espnow_link.h"
#include "peer_registry.h"

// -------------------- Config --------------------
static const uint8_t PROTO = 1;

// Same channel as Pump (1/6/11 recommended)
static const int WIFI_CHANNEL = 6;

// USB serial
static const int SERIAL_BAUD = 921600;

// ESP-NOW reliability
static const uint32_t ACK_TIMEOUT_MS = 120;
static const uint8_t  MAX_RETRY = 3;

// Status push to host (USB)
static const uint32_t STATUS_PUSH_MS = 200; // 5 Hz
static const uint32_t PUMP_OFFLINE_MS = 1200;

// -------------------- State --------------------
static EspNowState g_now_state{};
static const PeerEntry* g_pump_peer = nullptr;

static uint16_t g_cmd_seq = 0;
static int32_t  g_target_milli_lpm = 0;
static uint8_t  g_flags = 0;

static int32_t  g_pump_max_milli_lpm = 10000;

// USB RX (COBS frames delimited by 0x00)
static uint8_t rxbuf[256];
static size_t  rxlen = 0;

static void on_now_recv(const uint8_t* mac_addr, const uint8_t* data, int len) {
  espnow_on_recv(mac_addr, data, len, PROTO, &g_now_state);
}

// -------------------- USB status push --------------------
static void usb_send_status(uint16_t seq_reply) {
  uint8_t payload[128];
  size_t off = 0;

  UsbHdr hdr{PROTO, USB_BRIDGE_STATUS, seq_reply, millis()};
  memcpy(payload + off, &hdr, sizeof(hdr));
  off += sizeof(hdr);

  // body layout (fixed):
  // u8  pump_link
  // u16 last_seen_div10
  // u16 last_ack_seq
  // u8  applied_code
  // u16 err_flags
  // u16 retry_count
  // u16 send_fail_count
  // i32 pump_max_milli_lpm
  uint32_t age_ms = (g_now_state.last_seen_ms == 0) ? 0xFFFFFFFFu : (millis() - g_now_state.last_seen_ms);
  uint8_t pump_link = (age_ms < PUMP_OFFLINE_MS) ? 1 : 0;
  uint16_t last_seen_div10 = (age_ms == 0xFFFFFFFFu)
                             ? 65535
                             : (uint16_t)min<uint32_t>(age_ms / 10, 65535);

  payload[off++] = pump_link;
  *(uint16_t*)(payload + off) = last_seen_div10; off += 2;
  *(uint16_t*)(payload + off) = g_now_state.last_ack_seq; off += 2;
  payload[off++] = g_now_state.last_applied;
  *(uint16_t*)(payload + off) = g_now_state.last_err; off += 2;
  *(uint16_t*)(payload + off) = g_now_state.retry_count; off += 2;
  *(uint16_t*)(payload + off) = g_now_state.send_fail_count; off += 2;
  *(int32_t*)(payload + off) = g_pump_max_milli_lpm; off += 4;

  uint16_t crc = crc16_ccitt_false(payload, off);
  *(uint16_t*)(payload + off) = crc; off += 2;

  uint8_t enc[256];
  size_t encl = cobs_encode(payload, off, enc);
  Serial.write(enc, encl);
  Serial.write((uint8_t)0x00);
}

// -------------------- USB RX --------------------
static void handle_usb_packet(const uint8_t* pkt, size_t len) {
  if (len < sizeof(UsbHdr) + 2) return;

  uint16_t got = *(const uint16_t*)(pkt + len - 2);
  uint16_t calc = crc16_ccitt_false(pkt, (size_t)len - 2);
  if (got != calc) return;

  const UsbHdr* h = (const UsbHdr*)pkt;
  if (h->proto != PROTO) return;

  const uint8_t* body = pkt + sizeof(UsbHdr);
  size_t body_len = len - sizeof(UsbHdr) - 2;

  if (h->type == USB_SET_FLOW) {
    if (body_len < 5) return;
    g_target_milli_lpm = *(const int32_t*)body;
    g_flags = *(const uint8_t*)(body + 4);

    g_cmd_seq++;
    g_now_state.retry_left = MAX_RETRY;
    g_now_state.wait_ack = true;
    espnow_send_flow(g_pump_peer->mac, PROTO, g_cmd_seq, g_target_milli_lpm, g_flags, millis(), &g_now_state);
    usb_send_status(h->seq);

  } else if (h->type == USB_SET_MAXLPM) {
    if (body_len < 4) return;
    g_pump_max_milli_lpm = *(const int32_t*)body;
    espnow_send_maxlpm(g_pump_peer->mac, PROTO, ++g_cmd_seq, g_pump_max_milli_lpm, millis(), &g_now_state);
    usb_send_status(h->seq);

  } else if (h->type == USB_PING) {
    usb_send_status(h->seq);
  }
}

static void usb_poll() {
  while (Serial.available()) {
    uint8_t b = (uint8_t)Serial.read();
    if (b == 0x00) {
      if (rxlen > 0) {
        uint8_t dec[256];
        size_t decl = 0;
        if (cobs_decode(rxbuf, rxlen, dec, &decl)) {
          handle_usb_packet(dec, decl);
        }
      }
      rxlen = 0;
    } else {
      if (rxlen < sizeof(rxbuf)) rxbuf[rxlen++] = b;
      else rxlen = 0; // overflow -> drop frame
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(50);

  espnow_begin(WIFI_CHANNEL);

  g_pump_peer = peer_get_pump_main();
  if (!g_pump_peer) {
    Serial.println("Pump peer missing");
    while (true) delay(1000);
  }

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed");
    while (true) delay(1000);
  }
  esp_now_register_recv_cb(on_now_recv);

  espnow_add_peer(g_pump_peer->mac);

  g_now_state.last_seen_ms = 0;

  Serial.print("BRIDGE MAC: ");
  Serial.println(WiFi.macAddress());

  Serial.println("Bridge ready (USB <-> ESP-NOW only).");
}

void loop() {
  usb_poll();

  if (g_now_state.wait_ack && g_now_state.retry_left > 0 && (millis() - g_now_state.last_send_ms) > ACK_TIMEOUT_MS) {
    g_now_state.retry_left--;
    g_now_state.retry_count++;
    espnow_send_flow(g_pump_peer->mac, PROTO, g_cmd_seq, g_target_milli_lpm, g_flags, millis(), &g_now_state);
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

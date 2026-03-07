#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "cobs_crc.h"
#include "bridge_proto.h"

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

// Pump MAC (your Pump-ESP): D4:E9:F4:FA:88:34
static uint8_t PUMP_MAC[6] = {0xD4, 0xE9, 0xF4, 0xFA, 0x88, 0x34};

// -------------------- State --------------------
static uint8_t  g_last_applied = 0;
static uint16_t g_last_err = 0;
static uint16_t g_last_ack_seq = 0;
static uint32_t g_last_seen_ms = 0;

static uint16_t g_cmd_seq = 0;
static int32_t  g_target_milli_lpm = 0;
static uint8_t  g_flags = 0;

// retry state
static bool     g_wait_ack = false;
static uint8_t  g_retry_left = 0;
static uint32_t g_last_send_ms = 0;

static uint16_t g_retry_count = 0;
static uint16_t g_send_fail_count = 0;

static int32_t  g_pump_max_milli_lpm = 10000;

// USB RX (COBS frames delimited by 0x00)
static uint8_t rxbuf[256];
static size_t  rxlen = 0;

// -------------------- ESP-NOW --------------------
static void add_pump_peer() {
  if (esp_now_is_peer_exist(PUMP_MAC)) return;
  esp_now_peer_info_t p{};
  memcpy(p.peer_addr, PUMP_MAC, 6);
  p.channel = WIFI_CHANNEL;
  p.encrypt = false;
  p.ifidx = WIFI_IF_STA;
  esp_err_t r = esp_now_add_peer(&p);
  if (r != ESP_OK) {
    // nothing fatal; status will show offline
  }
}

static void now_send_flow() {
  NowCmdFlow pkt{};
  pkt.h = {PROTO, NOW_CMD_FLOW, g_cmd_seq};
  pkt.target_milli_lpm = g_target_milli_lpm;
  pkt.flags = g_flags;
  pkt.crc = crc16_ccitt_false((uint8_t*)&pkt, sizeof(pkt) - 2);

  esp_err_t r = esp_now_send(PUMP_MAC, (uint8_t*)&pkt, sizeof(pkt));
  if (r != ESP_OK) g_send_fail_count++;
  g_last_send_ms = millis();
}

static void now_send_maxlpm() {
  NowSetMaxLpm pkt{};
  pkt.h = {PROTO, NOW_SET_MAXLPM, ++g_cmd_seq};
  pkt.pump_max_milli_lpm = g_pump_max_milli_lpm;
  pkt.crc = crc16_ccitt_false((uint8_t*)&pkt, sizeof(pkt) - 2);

  esp_err_t r = esp_now_send(PUMP_MAC, (uint8_t*)&pkt, sizeof(pkt));
  if (r != ESP_OK) g_send_fail_count++;
  g_last_send_ms = millis();
}

static void on_now_recv(const uint8_t* mac_addr, const uint8_t* data, int len) {
  (void)mac_addr;
  if (!data || len < (int)sizeof(NowHdr) + 2) return;

  const NowHdr* h = (const NowHdr*)data;
  if (h->proto != PROTO) return;

  uint16_t got = *(const uint16_t*)(data + len - 2);
  uint16_t calc = crc16_ccitt_false(data, (size_t)len - 2);
  if (got != calc) return;

  g_last_seen_ms = millis();

  if (h->type == NOW_ACK && len == (int)sizeof(NowAck)) {
    const NowAck* a = (const NowAck*)data;
    g_last_ack_seq = a->h.seq;
    g_last_applied = a->applied_code;
    g_last_err = a->err_flags;
    g_wait_ack = false;

  } else if (h->type == NOW_STATUS && len == (int)sizeof(NowStatus)) {
    const NowStatus* s = (const NowStatus*)data;
    g_last_ack_seq = s->h.seq;
    g_last_applied = s->applied_code;
    g_last_err = s->err_flags;
    g_wait_ack = false;
  }
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
  uint32_t age_ms = (g_last_seen_ms == 0) ? 0xFFFFFFFFu : (millis() - g_last_seen_ms);
  uint8_t pump_link = (age_ms < PUMP_OFFLINE_MS) ? 1 : 0;
  uint16_t last_seen_div10 = (age_ms == 0xFFFFFFFFu)
                             ? 65535
                             : (uint16_t)min<uint32_t>(age_ms / 10, 65535);

  payload[off++] = pump_link;
  *(uint16_t*)(payload + off) = last_seen_div10; off += 2;
  *(uint16_t*)(payload + off) = g_last_ack_seq; off += 2;
  payload[off++] = g_last_applied;
  *(uint16_t*)(payload + off) = g_last_err; off += 2;
  *(uint16_t*)(payload + off) = g_retry_count; off += 2;
  *(uint16_t*)(payload + off) = g_send_fail_count; off += 2;
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
    g_retry_left = MAX_RETRY;
    g_wait_ack = true;
    now_send_flow();
    usb_send_status(h->seq);

  } else if (h->type == USB_SET_MAXLPM) {
    if (body_len < 4) return;
    g_pump_max_milli_lpm = *(const int32_t*)body;
    now_send_maxlpm();
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

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed");
    while (true) delay(1000);
  }
  esp_now_register_recv_cb(on_now_recv);

  add_pump_peer();

  g_last_seen_ms = 0;

  Serial.print("BRIDGE MAC: ");
  Serial.println(WiFi.macAddress());

  Serial.println("Bridge ready (USB <-> ESP-NOW only).");
}

void loop() {
  usb_poll();

  if (g_wait_ack && g_retry_left > 0 && (millis() - g_last_send_ms) > ACK_TIMEOUT_MS) {
    g_retry_left--;
    g_retry_count++;
    now_send_flow();
  }
  if (g_wait_ack && g_retry_left == 0 && (millis() - g_last_send_ms) > ACK_TIMEOUT_MS) {
    g_wait_ack = false;
  }

  static uint32_t last = 0;
  if (millis() - last >= STATUS_PUSH_MS) {
    last = millis();
    usb_send_status(0);
  }

  delay(1);
}

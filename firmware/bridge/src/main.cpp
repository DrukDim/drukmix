#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>

#include "bridge_config.h"
#include "bridge_proto.h"
#include "espnow_link.h"
#include "usb_link.h"
#include "peer_table.h"
#include "dmbus_hello.h"
#include "drukmix_bus_v1.h"
#include "drukmix_bus_util.h"
#ifndef BUILD_GIT_HASH
#define BUILD_GIT_HASH "dev"
#endif

static EspNowState g_now_state{};
static PeerTable g_peer_table{};
static PeerRecord g_active_pump{};
static bool g_active_pump_bound = false;

static uint16_t g_cmd_seq = 0;
static int32_t  g_target_milli_lpm = 0;
static uint8_t  g_flags = 0;
static int32_t  g_pump_max_milli_lpm = 10000;
static uint16_t g_reset_selector = 0;

enum PendingCmd : uint8_t {
  PENDING_NONE = 0,
  PENDING_FLOW = 1,
  PENDING_MAXLPM = 2,
  PENDING_RESET_FAULT = 3,
};

static PendingCmd g_pending_cmd = PENDING_NONE;

static UsbLink g_usb;

static uint32_t pending_ack_timeout_ms() {
  if (g_pending_cmd == PENDING_RESET_FAULT) return 1500;
  return ACK_TIMEOUT_MS;
}

static bool parse_hello_peer(
    const uint8_t* mac_addr,
    const uint8_t* data,
    int len,
    PeerRecord* out) {
  if (!mac_addr || !data || !out) return false;
  if (len < (int)(sizeof(dmbus::Header) + sizeof(dmbus::Hello) + sizeof(dmbus::FrameCrc))) return false;
  if (!dmbus::frame_valid(data, (size_t)len)) return false;

  const auto* h = reinterpret_cast<const dmbus::Header*>(data);
  if (h->msg_type != dmbus::MSG_HELLO) return false;
  if (h->payload_len != sizeof(dmbus::Hello)) return false;

  const auto* hello = reinterpret_cast<const dmbus::Hello*>(data + sizeof(dmbus::Header));
  if (hello->device_class != dmbus::DEV_PUMP) return false;

  PeerRecord peer{};
  peer.used = true;
  peer.node_id = hello->proposed_node_id;
  peer.device_class = hello->device_class;
  peer.driver_type = hello->driver_type;
  peer.hardware_uid_lo = hello->hardware_uid_lo;
  peer.hardware_uid_hi = hello->hardware_uid_hi;
  memcpy(peer.mac, mac_addr, 6);
  peer.last_seen_ms = millis();
  *out = peer;
  return true;
}

static const PeerRecord* active_pump_peer() {
  return g_active_pump_bound ? &g_active_pump : nullptr;
}

static void on_now_recv(const uint8_t* mac_addr, const uint8_t* data, int len) {
  PeerRecord hello_peer{};
  if (!g_active_pump_bound && parse_hello_peer(mac_addr, data, len, &hello_peer)) {
    g_active_pump = hello_peer;
    g_active_pump_bound = true;
  }

  if (dmbus_try_handle_hello(mac_addr, data, len, &g_peer_table, millis())) {
    return;
  }
  if (!g_active_pump_bound) return;
  espnow_on_recv(
      mac_addr,
      data,
      len,
      g_active_pump.mac,
      g_active_pump.node_id,
      BRIDGE_PROTO,
      &g_now_state);
}

static void usb_send_status(uint16_t seq_reply) {
  const auto* p = active_pump_peer();
  uint32_t age_ms = (!p)
      ? 0xFFFFFFFFu
      : max<uint32_t>(millis() - g_now_state.last_seen_ms, 0u);

  UsbStatusPayload st{};
  st.pump_link = (p && g_now_state.last_seen_ms != 0 && age_ms < DEVICE_OFFLINE_MS);
  st.last_seen_div10 = (age_ms == 0xFFFFFFFFu)
      ? 65535
      : (uint16_t)min<uint32_t>(age_ms / 10, 65535);
  st.last_ack_seq = g_now_state.last_ack_seq;
  st.applied_code = g_now_state.last_applied;
  st.err_flags = g_now_state.last_err;
  st.retry_count = g_now_state.retry_count;
  st.send_fail_count = g_now_state.send_fail_count;
  st.pump_max_milli_lpm = g_pump_max_milli_lpm;

  st.pump_state = g_now_state.pump_state;
  st.pump_mode = g_now_state.pump_mode;
  st.pump_fault_code = g_now_state.pump_fault_code;
  st.pump_online = g_now_state.pump_online;
  st.pump_running = g_now_state.pump_running;
  st.target_milli_lpm = g_now_state.target_milli_lpm;
  st.actual_milli_lpm = g_now_state.actual_milli_lpm;
  st.hw_setpoint_raw = g_now_state.hw_setpoint_raw;
  st.pump_flags = g_now_state.pump_flags;

  g_usb.send_status(BRIDGE_PROTO, seq_reply, st);
}

static void handle_usb_packet(const uint8_t* pkt, size_t len) {
  UsbHdr hdr{};
  const uint8_t* body = nullptr;
  size_t body_len = 0;

  if (!UsbLink::parse_packet(pkt, len, &hdr, &body, &body_len)) return;
  if (hdr.proto != BRIDGE_PROTO) return;

  if (hdr.type == USB_SET_FLOW) {
    if (body_len < 5) return;

    const auto* p = active_pump_peer();
    if (!p) {
      usb_send_status(hdr.seq);
      return;
    }

    g_target_milli_lpm = *(const int32_t*)body;
    g_flags = *(const uint8_t*)(body + 4);

    g_cmd_seq++;
    g_now_state.pending_seq = g_cmd_seq;
    g_now_state.retry_left = MAX_RETRY;
    g_now_state.wait_ack = true;
    g_pending_cmd = PENDING_FLOW;

    espnow_add_peer(p->mac);
    espnow_send_flow(
        p->mac,
        p->node_id,
        BRIDGE_PROTO,
        g_cmd_seq,
        g_target_milli_lpm,
        g_flags,
        millis(),
        &g_now_state);

    usb_send_status(hdr.seq);

  } else if (hdr.type == USB_SET_MAXLPM) {
    if (body_len < 4) return;

    const auto* p = active_pump_peer();
    if (!p) {
      usb_send_status(hdr.seq);
      return;
    }

    g_pump_max_milli_lpm = *(const int32_t*)body;
    ++g_cmd_seq;
    g_now_state.pending_seq = g_cmd_seq;
    g_now_state.retry_left = MAX_RETRY;
    g_now_state.wait_ack = true;
    g_pending_cmd = PENDING_MAXLPM;

    espnow_add_peer(p->mac);
    espnow_send_maxlpm(
        p->mac,
        p->node_id,
        BRIDGE_PROTO,
        g_cmd_seq,
        g_pump_max_milli_lpm,
        millis(),
        &g_now_state);

    usb_send_status(hdr.seq);

  } else if (hdr.type == USB_RESET_FAULT) {
    if (body_len < 2) return;

    const auto* p = active_pump_peer();
    if (!p) {
      usb_send_status(hdr.seq);
      return;
    }

    uint16_t selector = *(const uint16_t*)body;
    g_reset_selector = selector;
    ++g_cmd_seq;
    g_now_state.pending_seq = g_cmd_seq;
    g_now_state.retry_left = 0;
    g_now_state.wait_ack = true;
    g_pending_cmd = PENDING_RESET_FAULT;

    espnow_add_peer(p->mac);
    espnow_send_reset_fault(
        p->mac,
        p->node_id,
        BRIDGE_PROTO,
        g_cmd_seq,
        selector,
        millis(),
        &g_now_state);

    usb_send_status(hdr.seq);

  } else if (hdr.type == USB_PING) {
    usb_send_status(hdr.seq);
  }
}

void setup() {
  g_usb.begin(SERIAL_BAUD);
  delay(50);

  Serial.println();
  Serial.println("=== BRIDGE BOOT ===");
  Serial.print("fw=");
  Serial.print(BRIDGE_FW_VER_MAJOR);
  Serial.print(".");
  Serial.print(BRIDGE_FW_VER_MINOR);
  Serial.print(".");
  Serial.print(BRIDGE_FW_VER_PATCH);
  Serial.print(" label=");
  Serial.print(BRIDGE_FW_VER_LABEL);
  Serial.print(" git=");
  Serial.println(BUILD_GIT_HASH);

  espnow_begin(WIFI_CHANNEL);

  if (esp_now_init() != ESP_OK) {
    while (true) delay(1000);
  }

  esp_now_register_recv_cb(on_now_recv);

}

void loop() {
  uint8_t pkt[256];
  size_t pkt_len = 0;
  if (g_usb.poll_packet(pkt, sizeof(pkt), &pkt_len)) {
    handle_usb_packet(pkt, pkt_len);
  }

  if (!g_now_state.wait_ack && g_now_state.pending_seq == 0 && g_pending_cmd != PENDING_NONE) {
    g_pending_cmd = PENDING_NONE;
  }

  if (g_now_state.wait_ack &&
      g_now_state.retry_left > 0 &&
      (millis() - g_now_state.last_send_ms) > pending_ack_timeout_ms()) {

    const auto* p = active_pump_peer();
    if (p) {
      g_now_state.retry_left--;
      g_now_state.retry_count++;

      espnow_add_peer(p->mac);

      if (g_pending_cmd == PENDING_FLOW) {
        espnow_send_flow(
            p->mac,
            p->node_id,
            BRIDGE_PROTO,
            g_cmd_seq,
            g_target_milli_lpm,
            g_flags,
            millis(),
            &g_now_state);
      } else if (g_pending_cmd == PENDING_MAXLPM) {
        espnow_send_maxlpm(
            p->mac,
            p->node_id,
            BRIDGE_PROTO,
            g_cmd_seq,
            g_pump_max_milli_lpm,
            millis(),
            &g_now_state);
      } else if (g_pending_cmd == PENDING_RESET_FAULT) {
        espnow_send_reset_fault(
            p->mac,
            p->node_id,
            BRIDGE_PROTO,
            g_cmd_seq,
            g_reset_selector,
            millis(),
            &g_now_state);
      } else {
        g_now_state.wait_ack = false;
        g_now_state.pending_seq = 0;
        g_pending_cmd = PENDING_NONE;
      }
    } else {
      g_now_state.wait_ack = false;
      g_now_state.pending_seq = 0;
      g_pending_cmd = PENDING_NONE;
    }
  }

  if (g_now_state.wait_ack &&
      g_now_state.retry_left == 0 &&
      (millis() - g_now_state.last_send_ms) > pending_ack_timeout_ms()) {
    g_now_state.wait_ack = false;
    g_now_state.pending_seq = 0;
    g_pending_cmd = PENDING_NONE;
  }

  static uint32_t last = 0;
  if (millis() - last >= STATUS_PUSH_MS) {
    last = millis();
    usb_send_status(0);
  }

  delay(1);
}

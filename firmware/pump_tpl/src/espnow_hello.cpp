#include "espnow_hello.h"
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "drukmix_bus_v1.h"
#include "drukmix_bus_util.h"

#pragma pack(push, 1)
struct HelloFrame {
  dmbus::Header h;
  dmbus::Hello  hello;
  dmbus::FrameCrc crc;
};
#pragma pack(pop)

void espnow_hello_begin(int wifi_channel) {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_channel(wifi_channel, WIFI_SECOND_CHAN_NONE);
  esp_now_init();
}

void espnow_print_local_mac() {
  Serial.print("NODE MAC: ");
  Serial.println(WiFi.macAddress());
}

void espnow_get_local_uid(uint32_t* uid_lo, uint32_t* uid_hi) {
  uint64_t mac = ESP.getEfuseMac();
  if (uid_lo) *uid_lo = (uint32_t)(mac & 0xFFFFFFFFu);
  if (uid_hi) *uid_hi = (uint32_t)((mac >> 32) & 0xFFFFFFFFu);
}

bool espnow_send_hello(
    uint8_t proto,
    uint16_t node_id,
    uint8_t device_class,
    uint8_t driver_type,
    uint8_t fw_major,
    uint8_t fw_minor,
    uint8_t fw_patch,
    uint32_t uid_lo,
    uint32_t uid_hi) {

  HelloFrame f{};
  f.h.proto_ver = proto;
  f.h.msg_type = dmbus::MSG_HELLO;
  f.h.seq = 1;
  f.h.src_node = node_id;
  f.h.dst_node = dmbus::NODE_BROADCAST;
  f.h.device_class = device_class;
  f.h.opcode = 0;
  f.h.payload_len = sizeof(dmbus::Hello);

  f.hello.hardware_uid_lo = uid_lo;
  f.hello.hardware_uid_hi = uid_hi;
  f.hello.proposed_node_id = node_id;
  f.hello.device_class = device_class;
  f.hello.driver_type = driver_type;
  f.hello.fw_major = fw_major;
  f.hello.fw_minor = fw_minor;
  f.hello.fw_patch = fw_patch;
  f.hello.caps_len = 0;

  f.crc.crc16 = dmbus::frame_crc((const uint8_t*)&f, sizeof(f) - sizeof(f.crc));

  uint8_t bcast[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

  if (!esp_now_is_peer_exist(bcast)) {
    esp_now_peer_info_t p{};
    memcpy(p.peer_addr, bcast, 6);
    p.channel = 0;
    p.encrypt = false;
    p.ifidx = WIFI_IF_STA;
    esp_now_add_peer(&p);
  }

  return esp_now_send(bcast, (const uint8_t*)&f, sizeof(f)) == ESP_OK;
}
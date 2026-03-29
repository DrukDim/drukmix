#include <Arduino.h>
#include "debug_config.h"
#include "vfd_m980_debug.h"
#include "wifi_portal.h"
#include "http_api.h"
#include "config_store.h"
#include "preset_store.h"

#ifndef BUILD_GIT_HASH
#define BUILD_GIT_HASH "dev"
#endif

static VfdM980Debug g_vfd;
static WifiPortal g_wifi;
static HttpApi g_api(&g_vfd, &g_wifi);
static ConfigStore g_config_store;
static PresetStore g_preset_store;

void setup() {
  Serial.begin(DEBUG_SERIAL_BAUD);
  delay(200);

  Serial.println();
  Serial.println("=== PUMP_VFD_DEBUG BOOT ===");
  Serial.print("git=");
  Serial.println(BUILD_GIT_HASH);
  Serial.print("modbus slave=");
  Serial.println(MODBUS_SLAVE_ID);
  Serial.print("uart baud=");
  Serial.println(UART_BAUD);
  Serial.print("pins rx/tx/rts=");
  Serial.print(UART_RX_PIN);
  Serial.print("/");
  Serial.print(UART_TX_PIN);
  Serial.print("/");
  Serial.println(UART_RTS_PIN);

  g_vfd.begin();
  bool cfg_ok = g_config_store.begin();
  bool preset_fs_ok = g_preset_store.begin();
  bool preset_defaults_ok = preset_fs_ok && g_preset_store.ensure_defaults();
  Serial.print("config_store=");
  Serial.println(cfg_ok ? "ok" : "failed");
  Serial.print("preset_store=");
  Serial.println(preset_fs_ok ? "ok" : "failed");
  Serial.print("preset_defaults=");
  Serial.println(preset_defaults_ok ? "ok" : "failed");

  bool wifi_ok = g_wifi.begin();
  Serial.print("wifi=");
  Serial.println(wifi_ok ? "connected" : "failed");
  if (wifi_ok) {
    Serial.print("ip=");
    Serial.println(g_wifi.ip_string());
  }

  g_api.begin();

  RuntimeSnapshot rt{};
  if (g_vfd.read_runtime_snapshot(&rt)) {
    Serial.println("runtime snapshot: ok");
    Serial.print("run_state=");
    Serial.println(rt.run_state);
    Serial.print("fault_code=");
    Serial.println(rt.fault_code);
    Serial.print("actual_freq_x10=");
    Serial.println(rt.actual_freq_x10);
    Serial.print("actual_speed_raw=");
    Serial.println(rt.actual_speed_raw);
    Serial.print("output_current_x10=");
    Serial.println(rt.output_current_x10);
    Serial.print("di_state=");
    Serial.println(rt.di_state);
  } else {
    Serial.println("runtime snapshot: failed");
  }
}

void loop() {
  g_api.handle_client();
  delay(2);
}

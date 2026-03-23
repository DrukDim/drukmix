#include <Arduino.h>
#include "pump_tpl_node.h"
#include "espnow_hello.h"
#include "node_identity.h"
#include "cfg/BuildConfig.h"

#define DM_STR_INNER(x) #x
#define DM_STR(x) DM_STR_INNER(x)
#ifndef BUILD_GIT_HASH
#define BUILD_GIT_HASH "dev"
#endif

static PumpTplNode g_node;

void setup() {
  uint32_t uid_lo = 0;
  uint32_t uid_hi = 0;

  Serial.begin(115200);
  delay(200);

  Serial.println();
  Serial.println("=== PUMP_TPL BOOT ===");
  Serial.print("fw=");
  Serial.print(FW_VER_MAJOR);
  Serial.print(".");
  Serial.print(FW_VER_MINOR);
  Serial.print(".");
  Serial.print(FW_VER_PATCH);
  Serial.print(" label=");
  Serial.print(FW_VER_LABEL);
  Serial.print(" git=");
  Serial.println(DM_STR(BUILD_GIT_HASH));

  espnow_hello_begin(PumpTpl::Cfg::WIFI_CHANNEL);
  espnow_get_local_uid(&uid_lo, &uid_hi);
  espnow_print_local_mac();

  bool ok = espnow_send_hello(
      PumpTpl::Cfg::PROTO,
      NODE_ID_PUMP_TPL,
      DEVICE_CLASS_PUMP,
      DRIVER_TYPE_PUMP_TPL,
      FW_VER_MAJOR,
      FW_VER_MINOR,
      FW_VER_PATCH,
      uid_lo,
      uid_hi);

  Serial.print("HELLO sent: ");
  Serial.println(ok ? "yes" : "no");

  g_node.begin();
}

void loop() {
  static uint32_t last_hello = 0;
  static uint32_t uid_lo = 0;
  static uint32_t uid_hi = 0;

  if (uid_lo == 0 && uid_hi == 0) {
    espnow_get_local_uid(&uid_lo, &uid_hi);
  }

  uint32_t now = millis();
  if (now - last_hello >= 1000) {
    last_hello = now;
    espnow_send_hello(
        PumpTpl::Cfg::PROTO,
        NODE_ID_PUMP_TPL,
        DEVICE_CLASS_PUMP,
        DRIVER_TYPE_PUMP_TPL,
        FW_VER_MAJOR,
        FW_VER_MINOR,
        FW_VER_PATCH,
        uid_lo,
        uid_hi);
  }

  g_node.update();
}

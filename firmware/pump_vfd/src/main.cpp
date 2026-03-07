#include <Arduino.h>
#include "dmbus_pump_node.h"
#include "pump_vfd_config.h"
#include "node_identity.h"
#include "espnow_hello.h"

static PumpVfdNode g_node;

void setup() {
  uint32_t uid_lo = 0;
  uint32_t uid_hi = 0;

  Serial.begin(115200);
  delay(200);

  espnow_hello_begin(WIFI_CHANNEL);
  espnow_get_local_uid(&uid_lo, &uid_hi);
  espnow_print_local_mac();

  bool ok = espnow_send_hello(
      PUMP_VFD_PROTO,
      NODE_ID_PUMP_VFD,
      DEVICE_CLASS_PUMP,
      DRIVER_TYPE_PUMP_VFD,
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
  g_node.update();
}

#include "dmbus_pump_node.h"
#include <Arduino.h>
#include "pump_vfd_config.h"

void DmBusPumpNodeVfd::begin() {
  Serial.begin(115200);
  delay(100);
  vfd_.begin();
  Serial.println("pump_vfd node bootstrap");
}

void DmBusPumpNodeVfd::update() {
  uint32_t now = millis();

  if (now - last_status_ms_ >= STATUS_PERIOD_MS) {
    last_status_ms_ = now;

    VfdStatus st{};
    if (vfd_.poll_status(&st)) {
      Serial.print("VFD online=");
      Serial.print(st.online);
      Serial.print(" running=");
      Serial.print(st.running);
      Serial.print(" fault=");
      Serial.print(st.fault_code);
      Serial.print(" freq_x10=");
      Serial.println(st.actual_freq_x10);
    } else {
      Serial.println("VFD poll failed");
    }
  }

  delay(2);
}

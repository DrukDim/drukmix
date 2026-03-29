#include <Arduino.h>
#include "debug_config.h"
#include "vfd_m980_debug.h"

#ifndef BUILD_GIT_HASH
#define BUILD_GIT_HASH "dev"
#endif

static VfdM980Debug g_vfd;

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
  delay(1000);
}

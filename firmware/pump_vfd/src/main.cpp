#include <Arduino.h>
#include "dmbus_pump_node.h"

static DmBusPumpNodeVfd g_node;

void setup() {
  g_node.begin();
}

void loop() {
  g_node.update();
}

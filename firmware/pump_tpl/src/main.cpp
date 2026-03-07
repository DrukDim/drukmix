#include <Arduino.h>
#include "pump_tpl_node.h"

static PumpTplNode g_node;

void setup() {
  g_node.begin();
}

void loop() {
  g_node.update();
}

#include <Arduino.h>
#include "logic/PumpLogic.h"

DrukMixPump::Logic::PumpLogic g_pump;

void setup() {
  g_pump.begin();
}

void loop() {
  g_pump.update();
}
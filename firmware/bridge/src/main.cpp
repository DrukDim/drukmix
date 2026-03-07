#include <Arduino.h>
#include "drukmix_bus_v1.h"
#include "drukmix_bus_util.h"

void setup() {
  Serial.begin(921600);
  delay(100);
  Serial.println("DrukMixBridge bootstrap");
}

void loop() {
  delay(1000);
}

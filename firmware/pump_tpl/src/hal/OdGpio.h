#pragma once
#include <Arduino.h>

namespace DrukMixPump::Hal {
  inline void od_on(int pin) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }

  inline void od_off(int pin) {
    pinMode(pin, INPUT); // hi-Z
  }
}
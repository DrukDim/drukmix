#pragma once
#include <Arduino.h>

class WifiPortal {
public:
  bool begin();
  bool connected() const;
  String ip_string() const;
  String ssid() const;
  int rssi() const;
};

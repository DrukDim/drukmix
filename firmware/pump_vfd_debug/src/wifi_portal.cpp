#include "wifi_portal.h"
#include <WiFi.h>
#include <WiFiManager.h>
#include "debug_config.h"

bool WifiPortal::begin() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(DEBUG_HOSTNAME);

  WiFiManager wm;
  wm.setHostname(DEBUG_HOSTNAME);
  wm.setConfigPortalBlocking(true);
  bool ok = wm.autoConnect(DEBUG_AP_NAME);
  return ok;
}

bool WifiPortal::connected() const {
  return WiFi.status() == WL_CONNECTED;
}

String WifiPortal::ip_string() const {
  return connected() ? WiFi.localIP().toString() : String("");
}

String WifiPortal::ssid() const {
  return connected() ? WiFi.SSID() : String("");
}

int WifiPortal::rssi() const {
  return connected() ? WiFi.RSSI() : 0;
}

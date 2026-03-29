#pragma once
#include <WebServer.h>
#include "vfd_m980_debug.h"
#include "wifi_portal.h"

class HttpApi {
public:
  HttpApi(VfdM980Debug* vfd, WifiPortal* wifi);

  void begin();
  void handle_client();

private:
  VfdM980Debug* vfd_;
  WifiPortal* wifi_;
  WebServer server_;

  void handle_root_();
  void handle_status_();
  void handle_read_();
  void handle_read_block_();
  void handle_write_();
  void handle_not_found_();

  bool parse_reg_(const String& value, uint16_t* out);
  bool parse_u16_(const String& value, uint16_t* out);
  String json_escape_(const String& value);
  void send_json_(int code, const String& body);
};

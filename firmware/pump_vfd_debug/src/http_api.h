#pragma once
#include <WebServer.h>
#include "vfd_m980_debug.h"
#include "wifi_portal.h"
#include "config_store.h"
#include "preset_store.h"

class HttpApi {
public:
  HttpApi(
      VfdM980Debug* vfd,
      WifiPortal* wifi,
      ConfigStore* config_store,
      PresetStore* preset_store);

  void begin();
  void handle_client();

private:
  VfdM980Debug* vfd_;
  WifiPortal* wifi_;
  ConfigStore* config_store_;
  PresetStore* preset_store_;
  WebServer server_;

  void handle_root_();
  void handle_status_();
  void handle_config_();
  void handle_config_modbus_();
  void handle_config_poll_();
  void handle_presets_list_();
  void handle_presets_get_();
  void handle_presets_save_();
  void handle_presets_load_();
  void handle_read_();
  void handle_read_block_();
  void handle_write_();
  void handle_not_found_();

  bool parse_bool_(const String& value, bool* out);
  bool parse_reg_(const String& value, uint16_t* out);
  bool parse_u16_(const String& value, uint16_t* out);
  bool parse_u32_(const String& value, uint32_t* out);
  bool parse_regs_csv_(const String& value, std::vector<uint16_t>* out);
  String json_escape_(const String& value);
  void send_json_(int code, const String& body);
};

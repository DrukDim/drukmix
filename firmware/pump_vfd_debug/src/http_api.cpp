#include "http_api.h"
#include "debug_config.h"

HttpApi::HttpApi(
    VfdM980Debug* vfd,
    WifiPortal* wifi,
    ConfigStore* config_store,
    PresetStore* preset_store,
    PollManager* poll_manager)
    : vfd_(vfd),
      wifi_(wifi),
      config_store_(config_store),
      preset_store_(preset_store),
      poll_manager_(poll_manager),
      server_(HTTP_PORT) {}

void HttpApi::begin() {
  server_.on("/", HTTP_GET, [this]() { handle_root_(); });
  server_.on("/api/status", HTTP_GET, [this]() { handle_status_(); });
  server_.on("/api/watch", HTTP_GET, [this]() { handle_watch_(); });
  server_.on("/api/config", HTTP_GET, [this]() { handle_config_(); });
  server_.on("/api/config/modbus", HTTP_POST, [this]() { handle_config_modbus_(); });
  server_.on("/api/config/poll", HTTP_POST, [this]() { handle_config_poll_(); });
  server_.on("/api/presets", HTTP_GET, [this]() { handle_presets_list_(); });
  server_.on("/api/presets/get", HTTP_GET, [this]() { handle_presets_get_(); });
  server_.on("/api/presets/save", HTTP_POST, [this]() { handle_presets_save_(); });
  server_.on("/api/presets/load", HTTP_POST, [this]() { handle_presets_load_(); });
  server_.on("/api/read", HTTP_GET, [this]() { handle_read_(); });
  server_.on("/api/read_block", HTTP_GET, [this]() { handle_read_block_(); });
  server_.on("/api/write", HTTP_POST, [this]() { handle_write_(); });
  server_.onNotFound([this]() { handle_not_found_(); });
  server_.begin();
}

void HttpApi::handle_client() {
  server_.handleClient();
}

void HttpApi::handle_root_() {
  String html;
  html += "<!doctype html><html><head><meta charset='utf-8'><title>pump_vfd_debug</title></head><body>";
  html += "<h1>pump_vfd_debug</h1>";
  html += "<p>Use /api/status, /api/watch, /api/config, /api/presets</p>";
  html += "<p>Read: /api/read?reg=0xF000</p>";
  html += "<p>Read block: /api/read_block?reg=0x1000&count=7</p>";
  html += "<p>POST /api/write with reg and value params.</p>";
  html += "</body></html>";
  server_.send(200, "text/html", html);
}

void HttpApi::handle_status_() {
  RuntimeSnapshot rt{};
  bool modbus_ok = vfd_ && vfd_->read_runtime_snapshot(&rt);
  ModbusConfig modbus_cfg = vfd_ ? vfd_->modbus_config() : ModbusConfig{};
  PollConfig poll_cfg{};
  SystemConfig sys_cfg{};
  bool have_poll_cfg = config_store_ && config_store_->load_poll_config(&poll_cfg);
  bool have_sys_cfg = config_store_ && config_store_->load_system_config(&sys_cfg);

  String body = "{";
  body += "\"ok\":true,";
  body += "\"device\":\"pump_vfd_debug\",";
  body += "\"wifi\":{";
  body += "\"connected\":" + String(wifi_ && wifi_->connected() ? "true" : "false") + ",";
  body += "\"ssid\":\"" + json_escape_(wifi_ ? wifi_->ssid() : String("")) + "\",";
  body += "\"ip\":\"" + json_escape_(wifi_ ? wifi_->ip_string() : String("")) + "\",";
  body += "\"rssi\":" + String(wifi_ ? wifi_->rssi() : 0);
  body += "},";
  body += "\"modbus\":{";
  body += "\"slave_id\":" + String(modbus_cfg.slave_id) + ",";
  body += "\"baud\":" + String(modbus_cfg.baud) + ",";
  body += "\"format\":\"8N1\",";
  body += "\"timeout_ms\":" + String(modbus_cfg.timeout_ms) + ",";
  body += "\"last_poll_ok\":" + String(modbus_ok ? "true" : "false");
  body += "},";
  body += "\"poll\":{";
  body += "\"enabled\":" + String(have_poll_cfg && poll_cfg.enabled ? "true" : "false") + ",";
  body += "\"interval_ms\":" + String(have_poll_cfg ? poll_cfg.interval_ms : 0);
  body += "},";
  body += "\"active_preset\":\"" + json_escape_(have_sys_cfg ? sys_cfg.active_preset : String("")) + "\",";
  body += "\"runtime\":{";
  body += "\"valid\":" + String(rt.valid ? "true" : "false") + ",";
  body += "\"run_state\":" + String(rt.run_state) + ",";
  body += "\"fault_code\":" + String(rt.fault_code) + ",";
  body += "\"actual_freq_x10\":" + String(rt.actual_freq_x10) + ",";
  body += "\"actual_speed_raw\":" + String(rt.actual_speed_raw) + ",";
  body += "\"output_current_x10\":" + String(rt.output_current_x10) + ",";
  body += "\"di_state\":" + String(rt.di_state);
  body += "}";
  body += "}";

  send_json_(200, body);
}

void HttpApi::handle_watch_() {
  if (!poll_manager_) {
    send_json_(500, "{\"ok\":false,\"error\":\"poll_manager_unavailable\"}");
    return;
  }

  WatchSnapshot watch{};
  if (!poll_manager_->get_snapshot(&watch)) {
    send_json_(500, "{\"ok\":false,\"error\":\"watch_snapshot_failed\"}");
    return;
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"preset\":\"" + json_escape_(watch.active_preset_name) + "\",";
  body += "\"poll\":{";
  body += "\"enabled\":" + String(watch.enabled ? "true" : "false") + ",";
  body += "\"interval_ms\":" + String(watch.interval_ms) + ",";
  body += "\"last_poll_ms\":" + String(watch.last_poll_ms) + ",";
  body += "\"last_ok\":" + String(watch.last_ok ? "true" : "false") + ",";
  body += "\"last_error\":\"" + json_escape_(watch.last_error) + "\"";
  body += "},";
  body += "\"values\":[";
  for (size_t i = 0; i < watch.values.size(); i++) {
    if (i) body += ",";
    char regbuf[8];
    snprintf(regbuf, sizeof(regbuf), "0x%04X", watch.values[i].reg);
    body += "{";
    body += "\"reg\":\"" + String(regbuf) + "\",";
    body += "\"value\":" + String(watch.values[i].value) + ",";
    body += "\"valid\":" + String(watch.values[i].valid ? "true" : "false");
    body += "}";
  }
  body += "]";
  body += "}";
  send_json_(200, body);
}

void HttpApi::handle_config_() {
  if (!config_store_) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_store_unavailable\"}");
    return;
  }

  ModbusConfig modbus{};
  PollConfig poll{};
  SystemConfig sys{};
  if (!config_store_->load_modbus_config(&modbus) ||
      !config_store_->load_poll_config(&poll) ||
      !config_store_->load_system_config(&sys)) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_load_failed\"}");
    return;
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"modbus\":{";
  body += "\"slave_id\":" + String(modbus.slave_id) + ",";
  body += "\"baud\":" + String(modbus.baud) + ",";
  body += "\"timeout_ms\":" + String(modbus.timeout_ms);
  body += "},";
  body += "\"poll\":{";
  body += "\"enabled\":" + String(poll.enabled ? "true" : "false") + ",";
  body += "\"interval_ms\":" + String(poll.interval_ms);
  body += "},";
  body += "\"system\":{";
  body += "\"active_preset\":\"" + json_escape_(sys.active_preset) + "\",";
  body += "\"schema_version\":" + String(sys.schema_version);
  body += "}";
  body += "}";
  send_json_(200, body);
}

void HttpApi::handle_config_modbus_() {
  if (!config_store_ || !vfd_) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_store_unavailable\"}");
    return;
  }

  ModbusConfig cfg{};
  if (!config_store_->load_modbus_config(&cfg)) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_load_failed\"}");
    return;
  }

  if (server_.hasArg("slave_id")) {
    if (!parse_u16_(server_.arg("slave_id"), &cfg.slave_id) || cfg.slave_id == 0 || cfg.slave_id > 247) {
      send_json_(400, "{\"ok\":false,\"error\":\"invalid_slave_id\"}");
      return;
    }
  }
  if (server_.hasArg("baud")) {
    if (!parse_u32_(server_.arg("baud"), &cfg.baud) || cfg.baud == 0) {
      send_json_(400, "{\"ok\":false,\"error\":\"invalid_baud\"}");
      return;
    }
  }
  if (server_.hasArg("timeout_ms")) {
    if (!parse_u32_(server_.arg("timeout_ms"), &cfg.timeout_ms) || cfg.timeout_ms == 0) {
      send_json_(400, "{\"ok\":false,\"error\":\"invalid_timeout_ms\"}");
      return;
    }
  }

  if (!config_store_->save_modbus_config(cfg)) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_save_failed\"}");
    return;
  }

  vfd_->apply_modbus_config(cfg);

  String body = "{";
  body += "\"ok\":true,";
  body += "\"modbus\":{";
  body += "\"slave_id\":" + String(cfg.slave_id) + ",";
  body += "\"baud\":" + String(cfg.baud) + ",";
  body += "\"timeout_ms\":" + String(cfg.timeout_ms);
  body += "}";
  body += "}";
  send_json_(200, body);
}

void HttpApi::handle_config_poll_() {
  if (!config_store_) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_store_unavailable\"}");
    return;
  }

  PollConfig cfg{};
  if (!config_store_->load_poll_config(&cfg)) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_load_failed\"}");
    return;
  }

  if (server_.hasArg("enabled")) {
    if (!parse_bool_(server_.arg("enabled"), &cfg.enabled)) {
      send_json_(400, "{\"ok\":false,\"error\":\"invalid_enabled\"}");
      return;
    }
  }
  if (server_.hasArg("interval_ms")) {
    if (!parse_u32_(server_.arg("interval_ms"), &cfg.interval_ms) || cfg.interval_ms == 0) {
      send_json_(400, "{\"ok\":false,\"error\":\"invalid_interval_ms\"}");
      return;
    }
  }

  if (!config_store_->save_poll_config(cfg)) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_save_failed\"}");
    return;
  }
  if (poll_manager_) {
    poll_manager_->reload_poll_config();
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"poll\":{";
  body += "\"enabled\":" + String(cfg.enabled ? "true" : "false") + ",";
  body += "\"interval_ms\":" + String(cfg.interval_ms);
  body += "}";
  body += "}";
  send_json_(200, body);
}

void HttpApi::handle_presets_list_() {
  if (!preset_store_) {
    send_json_(500, "{\"ok\":false,\"error\":\"preset_store_unavailable\"}");
    return;
  }

  std::vector<String> names;
  if (!preset_store_->list_presets(&names)) {
    send_json_(500, "{\"ok\":false,\"error\":\"preset_list_failed\"}");
    return;
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"items\":[";
  for (size_t i = 0; i < names.size(); i++) {
    if (i) body += ",";
    body += "\"" + json_escape_(names[i]) + "\"";
  }
  body += "]}";
  send_json_(200, body);
}

void HttpApi::handle_presets_get_() {
  if (!preset_store_) {
    send_json_(500, "{\"ok\":false,\"error\":\"preset_store_unavailable\"}");
    return;
  }

  String name = server_.arg("name");
  if (name.length() == 0) {
    send_json_(400, "{\"ok\":false,\"error\":\"missing_name\"}");
    return;
  }

  RegisterPreset preset;
  if (!preset_store_->load_preset(name, &preset)) {
    send_json_(404, "{\"ok\":false,\"error\":\"preset_not_found\"}");
    return;
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"name\":\"" + json_escape_(preset.name) + "\",";
  body += "\"registers\":[";
  for (size_t i = 0; i < preset.regs.size(); i++) {
    if (i) body += ",";
    char buf[8];
    snprintf(buf, sizeof(buf), "0x%04X", preset.regs[i]);
    body += "\"" + String(buf) + "\"";
  }
  body += "]}";
  send_json_(200, body);
}

void HttpApi::handle_presets_save_() {
  if (!preset_store_) {
    send_json_(500, "{\"ok\":false,\"error\":\"preset_store_unavailable\"}");
    return;
  }

  RegisterPreset preset;
  preset.name = server_.arg("name");
  if (preset.name.length() == 0) {
    send_json_(400, "{\"ok\":false,\"error\":\"missing_name\"}");
    return;
  }
  if (!parse_regs_csv_(server_.arg("regs"), &preset.regs) || preset.regs.empty()) {
    send_json_(400, "{\"ok\":false,\"error\":\"invalid_regs\"}");
    return;
  }

  if (!preset_store_->save_preset(preset)) {
    send_json_(500, "{\"ok\":false,\"error\":\"preset_save_failed\"}");
    return;
  }
  if (poll_manager_ && config_store_) {
    SystemConfig sys{};
    if (config_store_->load_system_config(&sys) && sys.active_preset == preset.name) {
      poll_manager_->reload_active_preset();
    }
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"name\":\"" + json_escape_(preset.name) + "\",";
  body += "\"count\":" + String(preset.regs.size());
  body += "}";
  send_json_(200, body);
}

void HttpApi::handle_presets_load_() {
  if (!preset_store_ || !config_store_) {
    send_json_(500, "{\"ok\":false,\"error\":\"storage_unavailable\"}");
    return;
  }

  String name = server_.arg("name");
  if (name.length() == 0) {
    send_json_(400, "{\"ok\":false,\"error\":\"missing_name\"}");
    return;
  }

  RegisterPreset preset;
  if (!preset_store_->load_preset(name, &preset)) {
    send_json_(404, "{\"ok\":false,\"error\":\"preset_not_found\"}");
    return;
  }

  SystemConfig sys{};
  if (!config_store_->load_system_config(&sys)) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_load_failed\"}");
    return;
  }
  sys.active_preset = name;
  if (!config_store_->save_system_config(sys)) {
    send_json_(500, "{\"ok\":false,\"error\":\"config_save_failed\"}");
    return;
  }
  if (poll_manager_) {
    poll_manager_->reload_active_preset();
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"active_preset\":\"" + json_escape_(name) + "\"";
  body += "}";
  send_json_(200, body);
}

void HttpApi::handle_read_() {
  uint16_t reg = 0;
  if (!parse_reg_(server_.arg("reg"), &reg)) {
    send_json_(400, "{\"ok\":false,\"error\":\"invalid_reg\"}");
    return;
  }

  uint16_t value = 0;
  if (!vfd_ || !vfd_->read_reg(reg, &value)) {
    send_json_(502, "{\"ok\":false,\"error\":\"read_failed\"}");
    return;
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"reg\":\"0x" + String(reg, HEX) + "\",";
  body += "\"value\":" + String(value);
  body += "}";
  send_json_(200, body);
}

void HttpApi::handle_read_block_() {
  uint16_t reg = 0;
  uint16_t count = 0;
  if (!parse_reg_(server_.arg("reg"), &reg)) {
    send_json_(400, "{\"ok\":false,\"error\":\"invalid_reg\"}");
    return;
  }
  if (!parse_u16_(server_.arg("count"), &count) || count == 0 || count > 16) {
    send_json_(400, "{\"ok\":false,\"error\":\"invalid_count\"}");
    return;
  }

  uint16_t values[16] = {0};
  if (!vfd_ || !vfd_->read_block(reg, count, values)) {
    send_json_(502, "{\"ok\":false,\"error\":\"read_failed\"}");
    return;
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"reg\":\"0x" + String(reg, HEX) + "\",";
  body += "\"count\":" + String(count) + ",";
  body += "\"values\":[";
  for (uint16_t i = 0; i < count; i++) {
    if (i) body += ",";
    body += String(values[i]);
  }
  body += "]}";
  send_json_(200, body);
}

void HttpApi::handle_write_() {
  uint16_t reg = 0;
  uint16_t value = 0;
  if (!parse_reg_(server_.arg("reg"), &reg)) {
    send_json_(400, "{\"ok\":false,\"error\":\"invalid_reg\"}");
    return;
  }
  if (!parse_u16_(server_.arg("value"), &value)) {
    send_json_(400, "{\"ok\":false,\"error\":\"invalid_value\"}");
    return;
  }

  if (!vfd_ || !vfd_->write_reg(reg, value)) {
    send_json_(502, "{\"ok\":false,\"error\":\"write_failed\"}");
    return;
  }

  String body = "{";
  body += "\"ok\":true,";
  body += "\"reg\":\"0x" + String(reg, HEX) + "\",";
  body += "\"value\":" + String(value);
  body += "}";
  send_json_(200, body);
}

void HttpApi::handle_not_found_() {
  send_json_(404, "{\"ok\":false,\"error\":\"not_found\"}");
}

bool HttpApi::parse_bool_(const String& value, bool* out) {
  if (!out || value.length() == 0) return false;
  if (value == "1" || value.equalsIgnoreCase("true") || value.equalsIgnoreCase("on")) {
    *out = true;
    return true;
  }
  if (value == "0" || value.equalsIgnoreCase("false") || value.equalsIgnoreCase("off")) {
    *out = false;
    return true;
  }
  return false;
}

bool HttpApi::parse_reg_(const String& value, uint16_t* out) {
  if (!out || value.length() == 0) return false;
  return parse_u16_(value, out);
}

bool HttpApi::parse_u16_(const String& value, uint16_t* out) {
  if (!out || value.length() == 0) return false;

  char* end = nullptr;
  unsigned long parsed = 0;
  if (value.startsWith("0x") || value.startsWith("0X")) {
    parsed = strtoul(value.c_str(), &end, 16);
  } else {
    parsed = strtoul(value.c_str(), &end, 10);
  }
  if (!end || *end != '\0' || parsed > 0xFFFFul) return false;
  *out = (uint16_t)parsed;
  return true;
}

bool HttpApi::parse_u32_(const String& value, uint32_t* out) {
  if (!out || value.length() == 0) return false;

  char* end = nullptr;
  unsigned long parsed = 0;
  if (value.startsWith("0x") || value.startsWith("0X")) {
    parsed = strtoul(value.c_str(), &end, 16);
  } else {
    parsed = strtoul(value.c_str(), &end, 10);
  }
  if (!end || *end != '\0') return false;
  *out = (uint32_t)parsed;
  return true;
}

bool HttpApi::parse_regs_csv_(const String& value, std::vector<uint16_t>* out) {
  if (!out || value.length() == 0) return false;
  out->clear();

  int start = 0;
  while (start < value.length()) {
    int comma = value.indexOf(',', start);
    String token = comma >= 0 ? value.substring(start, comma) : value.substring(start);
    token.trim();
    uint16_t reg = 0;
    if (!parse_reg_(token, &reg)) return false;
    out->push_back(reg);
    if (comma < 0) break;
    start = comma + 1;
  }

  return !out->empty();
}

String HttpApi::json_escape_(const String& value) {
  String out;
  out.reserve(value.length() + 4);
  for (size_t i = 0; i < value.length(); i++) {
    char c = value[i];
    if (c == '\\' || c == '"') out += '\\';
    out += c;
  }
  return out;
}

void HttpApi::send_json_(int code, const String& body) {
  server_.send(code, "application/json", body);
}

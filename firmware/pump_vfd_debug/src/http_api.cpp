#include "http_api.h"
#include "debug_config.h"

HttpApi::HttpApi(VfdM980Debug* vfd, WifiPortal* wifi)
    : vfd_(vfd), wifi_(wifi), server_(HTTP_PORT) {}

void HttpApi::begin() {
  server_.on("/", HTTP_GET, [this]() { handle_root_(); });
  server_.on("/api/status", HTTP_GET, [this]() { handle_status_(); });
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
  html += "<p>Use /api/status, /api/read?reg=0xF000, /api/read_block?reg=0x1000&count=7</p>";
  html += "<p>POST /api/write with reg and value params.</p>";
  html += "</body></html>";
  server_.send(200, "text/html", html);
}

void HttpApi::handle_status_() {
  RuntimeSnapshot rt{};
  bool modbus_ok = vfd_ && vfd_->read_runtime_snapshot(&rt);

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
  body += "\"slave_id\":" + String(MODBUS_SLAVE_ID) + ",";
  body += "\"baud\":" + String(UART_BAUD) + ",";
  body += "\"format\":\"8N1\",";
  body += "\"last_poll_ok\":" + String(modbus_ok ? "true" : "false");
  body += "},";
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

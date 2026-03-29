#include "preset_store.h"
#include <LittleFS.h>
#include <ArduinoJson.h>

static constexpr char PRESETS_PATH[] = "/presets.json";

static void add_default_presets_(JsonObject presets) {
  JsonArray runtime = presets["runtime"].to<JsonArray>();
  runtime.add("0x1000");
  runtime.add("0x1001");
  runtime.add("0x1003");
  runtime.add("0x1004");
  runtime.add("0x1006");
  runtime.add("0x100B");

  JsonArray mode = presets["mode-switch"].to<JsonArray>();
  mode.add("0xF000");
  mode.add("0xF001");
  mode.add("0xF012");
  mode.add("0xF014");
  mode.add("0xF105");
  mode.add("0xF106");
  mode.add("0x100B");

  JsonArray modbus = presets["modbus"].to<JsonArray>();
  modbus.add("0xF700");
  modbus.add("0xF701");
  modbus.add("0xF702");
  modbus.add("0xF703");

  JsonArray motor = presets["motor"].to<JsonArray>();
  motor.add("0xF800");
  motor.add("0xF801");
  motor.add("0xF802");
  motor.add("0xF803");
  motor.add("0xF804");
  motor.add("0xF806");
  motor.add("0xF807");
}

static bool write_doc_(JsonDocument& doc) {
  File f = LittleFS.open(PRESETS_PATH, "w");
  if (!f) return false;
  bool ok = serializeJson(doc, f) > 0;
  f.close();
  return ok;
}

static bool read_doc_(JsonDocument& doc) {
  File f = LittleFS.open(PRESETS_PATH, "r");
  if (!f) return false;
  DeserializationError err = deserializeJson(doc, f);
  f.close();
  return !err;
}

bool PresetStore::begin() {
  return LittleFS.begin(true);
}

bool PresetStore::ensure_defaults() {
  JsonDocument doc;
  if (!read_doc_(doc)) {
    doc["version"] = 1;
    doc["presets"].to<JsonObject>();
  }

  doc["version"] = 1;
  JsonObject presets = doc["presets"].to<JsonObject>();
  add_default_presets_(presets);
  return write_doc_(doc);
}

bool PresetStore::list_presets(std::vector<String>* out) {
  if (!out) return false;
  out->clear();

  JsonDocument doc;
  if (!read_doc_(doc)) return false;

  JsonObject presets = doc["presets"].as<JsonObject>();
  for (JsonPair kv : presets) {
    out->push_back(String(kv.key().c_str()));
  }
  return true;
}

bool PresetStore::load_preset(const String& name, RegisterPreset* out) {
  if (!out) return false;
  out->name = name;
  out->regs.clear();

  JsonDocument doc;
  if (!read_doc_(doc)) return false;

  JsonArray arr = doc["presets"][name].as<JsonArray>();
  if (arr.isNull()) return false;

  for (JsonVariant v : arr) {
    String reg = v.as<String>();
    char* end = nullptr;
    unsigned long parsed = strtoul(reg.c_str(), &end, 16);
    if (!end || *end != '\0' || parsed > 0xFFFFul) continue;
    out->regs.push_back((uint16_t)parsed);
  }

  return true;
}

bool PresetStore::save_preset(const RegisterPreset& preset) {
  if (preset.name.length() == 0) return false;

  JsonDocument doc;
  if (!read_doc_(doc)) {
    doc["version"] = 1;
    doc["presets"].to<JsonObject>();
  }

  JsonArray arr = doc["presets"][preset.name].to<JsonArray>();
  arr.clear();
  for (uint16_t reg : preset.regs) {
    char buf[8];
    snprintf(buf, sizeof(buf), "0x%04X", reg);
    arr.add(buf);
  }

  return write_doc_(doc);
}

bool PresetStore::delete_preset(const String& name) {
  JsonDocument doc;
  if (!read_doc_(doc)) return false;
  JsonObject presets = doc["presets"].as<JsonObject>();
  if (presets.isNull() || !presets[name].is<JsonVariant>()) return false;
  presets.remove(name);
  return write_doc_(doc);
}

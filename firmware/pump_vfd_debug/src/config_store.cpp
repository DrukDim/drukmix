#include "config_store.h"
#include <Preferences.h>

static constexpr char NS_NAME[] = "vfddbg";
static constexpr char KEY_SLAVE_ID[] = "slave_id";
static constexpr char KEY_BAUD[] = "baud";
static constexpr char KEY_TIMEOUT[] = "timeout_ms";
static constexpr char KEY_POLL_EN[] = "poll_en";
static constexpr char KEY_POLL_MS[] = "poll_ms";
static constexpr char KEY_PRESET[] = "preset";
static constexpr char KEY_CFG_VER[] = "cfg_ver";

bool ConfigStore::begin() {
  Preferences prefs;
  if (!prefs.begin(NS_NAME, false)) return false;

  if (!prefs.isKey(KEY_CFG_VER)) {
    prefs.putUInt(KEY_CFG_VER, 1);
    prefs.putUShort(KEY_SLAVE_ID, 1);
    prefs.putULong(KEY_BAUD, 9600);
    prefs.putULong(KEY_TIMEOUT, 120);
    prefs.putBool(KEY_POLL_EN, true);
    prefs.putULong(KEY_POLL_MS, 1000);
    prefs.putString(KEY_PRESET, "runtime");
  }

  prefs.end();
  return true;
}

bool ConfigStore::load_modbus_config(ModbusConfig* out) {
  if (!out) return false;
  Preferences prefs;
  if (!prefs.begin(NS_NAME, true)) return false;
  out->slave_id = prefs.getUShort(KEY_SLAVE_ID, 1);
  out->baud = prefs.getULong(KEY_BAUD, 9600);
  out->timeout_ms = prefs.getULong(KEY_TIMEOUT, 120);
  prefs.end();
  return true;
}

bool ConfigStore::save_modbus_config(const ModbusConfig& cfg) {
  Preferences prefs;
  if (!prefs.begin(NS_NAME, false)) return false;
  prefs.putUShort(KEY_SLAVE_ID, cfg.slave_id);
  prefs.putULong(KEY_BAUD, cfg.baud);
  prefs.putULong(KEY_TIMEOUT, cfg.timeout_ms);
  prefs.end();
  return true;
}

bool ConfigStore::load_poll_config(PollConfig* out) {
  if (!out) return false;
  Preferences prefs;
  if (!prefs.begin(NS_NAME, true)) return false;
  out->enabled = prefs.getBool(KEY_POLL_EN, true);
  out->interval_ms = prefs.getULong(KEY_POLL_MS, 1000);
  prefs.end();
  return true;
}

bool ConfigStore::save_poll_config(const PollConfig& cfg) {
  Preferences prefs;
  if (!prefs.begin(NS_NAME, false)) return false;
  prefs.putBool(KEY_POLL_EN, cfg.enabled);
  prefs.putULong(KEY_POLL_MS, cfg.interval_ms);
  prefs.end();
  return true;
}

bool ConfigStore::load_system_config(SystemConfig* out) {
  if (!out) return false;
  Preferences prefs;
  if (!prefs.begin(NS_NAME, true)) return false;
  out->active_preset = prefs.getString(KEY_PRESET, "runtime");
  out->schema_version = prefs.getUInt(KEY_CFG_VER, 1);
  prefs.end();
  return true;
}

bool ConfigStore::save_system_config(const SystemConfig& cfg) {
  Preferences prefs;
  if (!prefs.begin(NS_NAME, false)) return false;
  prefs.putString(KEY_PRESET, cfg.active_preset);
  prefs.putUInt(KEY_CFG_VER, cfg.schema_version);
  prefs.end();
  return true;
}

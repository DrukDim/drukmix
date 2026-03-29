#include "poll_manager.h"

PollManager::PollManager(
    VfdM980Debug* vfd,
    ConfigStore* config_store,
    PresetStore* preset_store)
    : vfd_(vfd),
      config_store_(config_store),
      preset_store_(preset_store) {}

bool PollManager::begin() {
  bool ok = reload_poll_config();
  ok = reload_active_preset() && ok;
  if (snapshot_.enabled) {
    poll_now_();
  }
  return ok;
}

void PollManager::update() {
  if (!snapshot_.enabled) return;

  uint32_t now = millis();
  if (snapshot_.last_poll_ms != 0 && (uint32_t)(now - snapshot_.last_poll_ms) < snapshot_.interval_ms) {
    return;
  }

  poll_now_();
}

bool PollManager::reload_poll_config() {
  if (!config_store_) return false;

  PollConfig cfg{};
  if (!config_store_->load_poll_config(&cfg)) return false;

  snapshot_.enabled = cfg.enabled;
  snapshot_.interval_ms = cfg.interval_ms;
  return true;
}

bool PollManager::reload_active_preset() {
  if (!config_store_ || !preset_store_) return false;

  SystemConfig sys{};
  if (!config_store_->load_system_config(&sys)) return false;

  RegisterPreset preset;
  if (!preset_store_->load_preset(sys.active_preset, &preset)) return false;

  snapshot_.active_preset_name = sys.active_preset;
  snapshot_.last_poll_ms = 0;
  snapshot_.last_ok = false;
  snapshot_.last_error = "";
  snapshot_.values.clear();
  snapshot_.values.reserve(preset.regs.size());
  for (uint16_t reg : preset.regs) {
    WatchValue item;
    item.reg = reg;
    snapshot_.values.push_back(item);
  }

  return true;
}

bool PollManager::get_snapshot(WatchSnapshot* out) const {
  if (!out) return false;
  *out = snapshot_;
  return true;
}

bool PollManager::poll_now_() {
  if (!vfd_) return false;

  snapshot_.last_poll_ms = millis();
  snapshot_.last_ok = true;
  snapshot_.last_error = "";

  for (size_t i = 0; i < snapshot_.values.size(); i++) {
    uint16_t value = 0;
    if (!vfd_->read_reg(snapshot_.values[i].reg, &value)) {
      snapshot_.values[i].valid = false;
      snapshot_.last_ok = false;
      char buf[24];
      snprintf(buf, sizeof(buf), "read_failed:0x%04X", snapshot_.values[i].reg);
      snapshot_.last_error = String(buf);
      return false;
    }
    snapshot_.values[i].value = value;
    snapshot_.values[i].valid = true;
  }

  return true;
}

#pragma once
#include <Arduino.h>
#include <vector>
#include "config_store.h"
#include "preset_store.h"
#include "vfd_m980_debug.h"

struct WatchValue {
  uint16_t reg = 0;
  uint16_t value = 0;
  bool valid = false;
};

struct WatchSnapshot {
  String active_preset_name;
  bool enabled = false;
  uint32_t interval_ms = 0;
  uint32_t last_poll_ms = 0;
  bool last_ok = false;
  String last_error;
  std::vector<WatchValue> values;
};

class PollManager {
public:
  PollManager(
      VfdM980Debug* vfd,
      ConfigStore* config_store,
      PresetStore* preset_store);

  bool begin();
  void update();

  bool reload_poll_config();
  bool reload_active_preset();
  bool get_snapshot(WatchSnapshot* out) const;

private:
  bool poll_now_();

  VfdM980Debug* vfd_;
  ConfigStore* config_store_;
  PresetStore* preset_store_;
  WatchSnapshot snapshot_;
};

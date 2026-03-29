#pragma once
#include <Arduino.h>
#include <vector>

struct RegisterPreset {
  String name;
  std::vector<uint16_t> regs;
};

class PresetStore {
public:
  bool begin();
  bool ensure_defaults();

  bool list_presets(std::vector<String>* out);
  bool load_preset(const String& name, RegisterPreset* out);
  bool save_preset(const RegisterPreset& preset);
  bool delete_preset(const String& name);
};

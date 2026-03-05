#pragma once

namespace DrukMixPump::Pins {
  // TPL0501 pins
  static constexpr int CS   = 16;
  static constexpr int MOSI = 17;
  static constexpr int SCLK = 18;

  // Switch sense: manual forward
  static constexpr int SW_FWD = 27;      // INPUT_PULLUP, pos1->GND

  // DIR_FORCE node sense & drive
  static constexpr int DIR_SENSE = 25;   // INPUT_PULLUP
  static constexpr int DIR_DRIVE = 33;   // open-drain style

  // WIPER relay (IN2)
  static constexpr int WIPER_DRIVE = 26; // open-drain style
}
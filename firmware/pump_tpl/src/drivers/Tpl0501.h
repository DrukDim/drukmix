#pragma once
#include <Arduino.h>
#include <SPI.h>

namespace PumpTpl::Drivers {

  class Tpl0501 {
   public:
    Tpl0501(int cs, int sclk, int mosi, uint32_t hz);
    void begin();

    // Always writes (double-write). Use for boot "force 0".
    void forceWrite(uint8_t code);

    // Writes only if changed.
    void apply(uint8_t code);

    uint8_t last() const { return last_; }

   private:
    int cs_, sclk_, mosi_;
    uint32_t hz_;
    SPIClass spi_;
    uint8_t last_;

    void writeOnce_(uint8_t code);
  };

}
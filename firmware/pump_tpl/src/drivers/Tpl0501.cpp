#include "Tpl0501.h"

using namespace PumpTpl::Drivers;

Tpl0501::Tpl0501(int cs, int sclk, int mosi, uint32_t hz)
: cs_(cs), sclk_(sclk), mosi_(mosi), hz_(hz), spi_(VSPI), last_(0) {}

void Tpl0501::begin() {
  pinMode(cs_, OUTPUT);
  digitalWrite(cs_, HIGH);
  spi_.begin(sclk_, -1, mosi_, cs_);
}

void Tpl0501::writeOnce_(uint8_t code) {
  spi_.beginTransaction(SPISettings(hz_, MSBFIRST, SPI_MODE0));
  digitalWrite(cs_, LOW);
  delayMicroseconds(5);
  spi_.transfer(code);
  delayMicroseconds(5);
  digitalWrite(cs_, HIGH);
  spi_.endTransaction();
}

void Tpl0501::forceWrite(uint8_t code) {
  writeOnce_(code);
  delayMicroseconds(50);
  writeOnce_(code);
  last_ = code;
}

void Tpl0501::apply(uint8_t code) {
  if (code == last_) return;
  forceWrite(code);
}
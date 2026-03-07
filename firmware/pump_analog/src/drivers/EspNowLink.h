#pragma once
#include <cstdint>
#include <esp_now.h>

namespace DrukMixPump::Drivers {

  struct RxCmd {
    bool valid = false;
    uint8_t type = 0;
    uint16_t seq = 0;
    int32_t target_milli_lpm = 0;
    uint8_t flags = 0;
    int32_t pump_max_milli_lpm = 0;
  };

  class EspNowLink {
   public:
    void begin(int wifi_channel, uint8_t proto);

    // call in loop: returns last received cmd (if any) and clears "valid"
    RxCmd popRxCmd();

    uint16_t getErrFlags() const { return err_flags_; }

    // send
    void sendAck(uint16_t seq, uint8_t applied_code, uint16_t err_flags, uint8_t proto);
    void sendStatus(uint16_t last_cmd_seq, uint8_t applied_code, uint16_t err_flags, uint32_t uptime_ms, uint8_t proto);

   private:
    static void onRecvThunk_(const uint8_t* mac_addr, const uint8_t* data, int data_len);
    void onRecv_(const uint8_t* mac_addr, const uint8_t* data, int data_len);

    void ensurePeer_(const uint8_t* mac);

    static EspNowLink* self_;

    bool peer_known_ = false;
    uint8_t peer_mac_[6] = {0};
    uint16_t err_flags_ = 0;

    RxCmd rx_;
    uint8_t proto_ = 1;
  };

}
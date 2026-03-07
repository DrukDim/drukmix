#pragma once
#include <stdint.h>

void espnow_hello_begin(int wifi_channel);
bool espnow_send_hello(
    uint8_t proto,
    uint16_t node_id,
    uint8_t device_class,
    uint8_t driver_type,
    uint8_t fw_major,
    uint8_t fw_minor,
    uint8_t fw_patch,
    uint32_t uid_lo,
    uint32_t uid_hi);
void espnow_print_local_mac();
void espnow_get_local_uid(uint32_t* uid_lo, uint32_t* uid_hi);

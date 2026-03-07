#pragma once
#include <stdint.h>
#include "peer_table.h"

bool dmbus_try_handle_hello(
    const uint8_t* mac_addr,
    const uint8_t* data,
    int len,
    PeerTable* table,
    uint32_t now_ms);

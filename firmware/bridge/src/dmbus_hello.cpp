#include "dmbus_hello.h"
#include <string.h>
#include "drukmix_bus_v1.h"
#include "drukmix_bus_util.h"

bool dmbus_try_handle_hello(
    const uint8_t* mac_addr,
    const uint8_t* data,
    int len,
    PeerTable* table,
    uint32_t now_ms) {

  if (!mac_addr || !data || !table) return false;
  if (len < (int)(sizeof(dmbus::Header) + sizeof(dmbus::Hello) + sizeof(dmbus::FrameCrc))) return false;
  if (!dmbus::frame_valid(data, (size_t)len)) return false;

  const auto* h = reinterpret_cast<const dmbus::Header*>(data);
  if (h->msg_type != dmbus::MSG_HELLO) return false;
  if (h->payload_len != sizeof(dmbus::Hello)) return false;

  const auto* hello = reinterpret_cast<const dmbus::Hello*>(data + sizeof(dmbus::Header));

  table->upsert(
      hello->proposed_node_id,
      hello->device_class,
      hello->driver_type,
      hello->hardware_uid_lo,
      hello->hardware_uid_hi,
      mac_addr,
      now_ms);

  return true;
}

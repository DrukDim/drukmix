#pragma once
#include <stdint.h>

namespace dmbus {

static constexpr uint8_t  PROTO_VER = 1;
static constexpr uint16_t NODE_BROADCAST  = 0xFFFF;
static constexpr uint16_t NODE_UNASSIGNED = 0x0000;

// ---------- Message types ----------
enum MsgType : uint8_t {
  MSG_HELLO        = 1,
  MSG_HELLO_ACK    = 2,
  MSG_CMD          = 3,
  MSG_ACK          = 4,
  MSG_STATUS       = 5,
  MSG_EVENT        = 6,
  MSG_FAULT        = 7,
  MSG_HEARTBEAT    = 8,
  MSG_DISCOVERY    = 9,
  MSG_DISCOVERY_R  = 10
};

// ---------- Device classes ----------
enum DeviceClass : uint8_t {
  DEV_BRIDGE  = 1,
  DEV_PUMP    = 2,
  DEV_MIXER   = 3,
  DEV_FEEDER  = 4,
  DEV_VALVE   = 5,
  DEV_SENSOR  = 6,
  DEV_IO      = 7,
  DEV_SERVICE = 8
};

// ---------- Driver types ----------
enum DriverType : uint8_t {
  DRV_UNKNOWN       = 0,
  DRV_PUMP_ANALOG   = 1,
  DRV_PUMP_MODBUS   = 2,
  DRV_MIXER_MODBUS  = 3,
  DRV_IO_RELAY      = 4,
  DRV_SENSOR_ADC    = 5
};

// ---------- Common opcodes ----------
enum CommonOpcode : uint8_t {
  OP_NOP             = 0,
  OP_IDENTIFY        = 1,
  OP_GET_STATUS      = 2,
  OP_GET_CAPS        = 3,
  OP_SET_MODE        = 4,
  OP_STOP            = 5,
  OP_RESET_FAULT     = 6,
  OP_HEARTBEAT       = 7
};

// ---------- Pump opcodes ----------
enum PumpOpcode : uint8_t {
  PUMP_SET_FLOW       = 32,
  PUMP_SET_MAX_FLOW   = 33,
  PUMP_PRIME          = 34,
  PUMP_FLUSH          = 35,
  PUMP_GET_TELEMETRY  = 36
};

// ---------- Mixer opcodes ----------
enum MixerOpcode : uint8_t {
  MIXER_SET_RATE       = 48,
  MIXER_SET_CHANNELS   = 49,
  MIXER_GET_TELEMETRY  = 50
};

enum AckStatus : uint8_t {
  ACK_OK          = 0,
  ACK_ERROR       = 1,
  ACK_BUSY        = 2,
  ACK_UNSUPPORTED = 3
};

enum State : uint16_t {
  STATE_BOOT      = 1,
  STATE_IDLE      = 2,
  STATE_READY     = 3,
  STATE_RUNNING   = 4,
  STATE_PAUSED    = 5,
  STATE_STOPPING  = 6,
  STATE_FAULT     = 7,
  STATE_OFFLINE   = 8
};

enum Mode : uint16_t {
  MODE_UNKNOWN = 0,
  MODE_LOCAL   = 1,
  MODE_REMOTE  = 2,
  MODE_AUTO    = 3,
  MODE_SERVICE = 4
};

enum ErrCode : uint16_t {
  ERR_NONE            = 0,
  ERR_BAD_CRC         = 1,
  ERR_BAD_PROTO       = 2,
  ERR_BAD_LEN         = 3,
  ERR_UNSUPPORTED     = 4,
  ERR_BAD_STATE       = 5,
  ERR_BAD_PARAM       = 6,
  ERR_BUSY            = 7,
  ERR_TIMEOUT         = 8,
  ERR_NOT_ENROLLED    = 9,
  ERR_ROUTE_MISS      = 10,
  ERR_HW_FAILURE      = 11
};

enum FaultCode : uint16_t {
  FAULT_NONE               = 0,
  FAULT_COMMS_LOSS         = 100,
  FAULT_WATCHDOG_TIMEOUT   = 101,
  FAULT_REMOTE_REJECTED    = 102,
  FAULT_HW_NOT_READY       = 103,
  FAULT_DRIVER_INTERNAL    = 104,
  FAULT_PUMP_DRYRUN        = 200,
  FAULT_PUMP_OVERCURRENT   = 201,
  FAULT_PUMP_VFD_FAULT     = 202,
  FAULT_PUMP_MANUAL_MODE   = 203
};

enum CapBits : uint32_t {
  CAP_REMOTE_STOP         = 1u << 0,
  CAP_SETPOINT_CONTROL    = 1u << 1,
  CAP_TELEMETRY           = 1u << 2,
  CAP_FAULT_RESET         = 1u << 3,
  CAP_ACTUAL_FEEDBACK     = 1u << 4,
  CAP_MULTI_CHANNEL       = 1u << 5,
  CAP_LOCAL_MANUAL_SENSE  = 1u << 6
};

enum PumpFlags : uint16_t {
  PUMP_FLAG_RUNNING       = 1u << 0,
  PUMP_FLAG_FORWARD       = 1u << 1,
  PUMP_FLAG_REVERSE       = 1u << 2,
  PUMP_FLAG_MANUAL_MODE   = 1u << 3,
  PUMP_FLAG_REMOTE_MODE   = 1u << 4,
  PUMP_FLAG_FAULT_LATCHED = 1u << 5,
  PUMP_FLAG_WDOG_STOP     = 1u << 6,
  PUMP_FLAG_HW_READY      = 1u << 7
};

enum LinkFlags : uint16_t {
  LINK_FLAG_ENROLLED      = 1u << 0,
  LINK_FLAG_KNOWN_PEER    = 1u << 1,
  LINK_FLAG_ACK_PENDING   = 1u << 2,
  LINK_FLAG_RETRYING      = 1u << 3
};

#pragma pack(push, 1)

struct Header {
  uint8_t  proto_ver;
  uint8_t  msg_type;
  uint16_t seq;
  uint16_t src_node;
  uint16_t dst_node;
  uint8_t  device_class;
  uint8_t  opcode;
  uint16_t payload_len;
};

struct Hello {
  uint32_t hardware_uid_lo;
  uint32_t hardware_uid_hi;
  uint16_t proposed_node_id;
  uint8_t  device_class;
  uint8_t  driver_type;
  uint8_t  fw_major;
  uint8_t  fw_minor;
  uint8_t  fw_patch;
  uint8_t  caps_len;
};

struct HelloAck {
  uint16_t assigned_node_id;
  uint8_t  accepted;
  uint8_t  enroll_state;
};

struct Ack {
  uint16_t ack_seq;
  uint8_t  status;
  uint8_t  reserved;
  uint16_t err_code;
  uint16_t detail;
};

struct Heartbeat {
  uint32_t uptime_ms;
  uint16_t state;
  uint16_t warn_flags;
  uint16_t fault_code;
};

struct StatusCommon {
  uint32_t uptime_ms;
  uint16_t state;
  uint16_t mode;
  uint16_t warn_flags;
  uint16_t fault_code;
  uint8_t  online;
  uint8_t  reserved;
};

struct CapsCommon {
  uint32_t cap_bits;
  uint8_t  driver_type;
  uint8_t  reserved[3];
};

struct SetMode {
  uint16_t mode;
};

struct Stop {
  uint8_t stop_type;
  uint8_t reserved[3];
};

struct ResetFault {
  uint16_t fault_selector;
};

struct PumpSetFlow {
  int32_t target_milli_lpm;
  uint8_t flags;
  uint8_t reserved[3];
};

struct PumpSetMaxFlow {
  int32_t max_milli_lpm;
};

struct PumpStatus {
  StatusCommon c;
  int32_t target_milli_lpm;
  int32_t actual_milli_lpm;
  int32_t max_milli_lpm;
  int32_t hw_setpoint_raw;
  int32_t actual_freq_x10;
  int16_t actual_speed_raw;
  uint16_t output_current_x10;
  uint16_t link_flags;
  uint16_t pump_flags;
};

struct FaultPayload {
  uint16_t fault_code;
  uint16_t detail_code;
  uint32_t arg0;
  uint32_t arg1;
};

struct EventPayload {
  uint16_t event_code;
  uint16_t detail_code;
  uint32_t arg0;
  uint32_t arg1;
};

struct FrameCrc {
  uint16_t crc16;
};

#pragma pack(pop)

static constexpr uint16_t header_size() { return sizeof(Header); }

} // namespace dmbus

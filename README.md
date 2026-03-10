# DrukMix

DrukMix is a control stack for a concrete 3D printing system built around Klipper, Moonraker, Mainsail, and external pump/mixer hardware.

The project goal is not a generic plastic FDM workflow. It is focused on a concrete extrusion machine with:
- screw-based extruder
- screw pump feeding material through a hose
- external pump driver hardware
- custom control logic integrated with print execution

## Project goals

The long-term goal is to build a stable and extensible control stack that can:
- synchronize pump flow with printing motion
- support multiple pump driver backends under one common model
- integrate with Klipper, Moonraker, and Mainsail
- support operational logic such as flush, prime, hard stop, minimum-flow cutoff, and fault handling
- remain version-pinned and modifiable without upstream updates breaking local changes

## Current architecture

The project is split into three main layers.

### 1. Pump node
An ESP-based hardware-side node located near the real pump driver.

Responsibilities:
- receive bus commands
- validate local operating conditions
- apply commands to the physical driver
- generate ACK frames
- generate STATUS frames

Non-responsibilities:
- print orchestration
- flush scheduling
- Klipper print policy
- UI logic

### 2. Bridge
A USB to ESP-NOW bridge.

Responsibilities:
- receive commands from the host
- forward them to the pump node
- track ACK timeout and retries
- expose bridge and pump status back to the host

The bridge should stay transport-oriented and should not accumulate print business logic.

### 3. Agent / host-side control
The host-side layer that will integrate with Klipper, Moonraker, and Mainsail.

Responsibilities:
- print-state integration
- flush / prime sequencing
- unconditional stop logic
- minimum-flow cutoff
- synchronization policy
- UI/state exposure to higher layers

## Canonical bus rules

### One abstract pump model
The system must expose one logical pump abstraction to upper layers.

Different hardware implementations may exist underneath:
- VFD / Modbus pump
- TPL / analog + relay pump
- future drivers

Upper layers should not care which pump driver is physically present.

### Canonical command set
Current canonical pump commands:
- `PUMP_SET_FLOW`
- `PUMP_SET_MAX_FLOW`
- `OP_STOP`
- `OP_RESET_FAULT`

Optional future commands:
- `PUMP_PRIME`
- `PUMP_FLUSH`

### Canonical ACK
There is one ACK format for pump commands:

    struct Ack {
      uint16_t ack_seq;
      uint8_t  status;
      uint8_t  reserved;
      uint16_t err_code;
      uint16_t detail;
    };

Semantics:
- `ack_seq` = acknowledged command sequence
- `status` = normalized result (`ACK_OK`, `ACK_ERROR`, `ACK_BUSY`, `ACK_UNSUPPORTED`)
- `err_code` = normalized system-level reason
- `detail` = backend-specific detail or raw driver error information

### Canonical pump status
There is one canonical runtime pump status type:
- `PumpStatus`

Canonical `PumpStatus` contains only backend-independent runtime fields:
- `StatusCommon c`
- `target_milli_lpm`
- `max_milli_lpm`
- `hw_setpoint_raw`
- `link_flags`
- `pump_flags`

Versioned duplicates such as `PumpStatusV1`, `PumpStatusV2`, etc. should not be introduced unless there is a hard compatibility requirement.

The status model must remain suitable for more than one backend. It must not become permanently VFD-specific.

It must not contain backend-only telemetry such as:
- VFD frequency
- VFD motor speed
- VFD output current

## Manual / local mode rule

Manual or local override is a core part of the system model.

If local/manual control is active:
- remote run commands must not be treated as normal run commands
- the node should report rejection through ACK
- the current manual/local state must be visible in status

This rule is required for:
- VFD-based pump control with a local selector/toggle
- future TPL/relay-based pump control with manual override inputs

## RS485 note

The current RS485 design uses shared `DE/RE` on one control pin.

This is acceptable for half-duplex operation as long as:
- TX mode is enabled before transmission
- the UART is flushed before switching back to RX
- turnaround timing is handled correctly

Shared `DE/RE` is not itself a blocker for receiving feedback from the VFD.

## Current direction

The project should avoid overgrowing the transport layer.

Target shape:
- one abstract pump model
- one ACK model
- one `PumpStatus` model
- bridge remains simple
- agent becomes the intelligent coordination layer

## What not to do

Do not:
- duplicate status structures without necessity
- move print business logic into the bridge
- let transport details dictate the whole architecture
- make the bus permanently specific to only one pump backend

## Canonical pump command semantics

The canonical host-visible pump command behavior is:

### `PUMP_SET_FLOW`
Purpose:
- request a pump flow target in `milli_lpm`

Rules:
- `target_milli_lpm > 0` means normal remote pumping request
- `target_milli_lpm <= 0` is not the preferred hard-stop command; it may be treated as a stop-equivalent by a backend, but host orchestration should prefer explicit stop semantics
- command acceptance must depend on current node state, hardware readiness, and local/manual override state
- backend-specific low-level actuation is private to the node

ACK expectations:
- `ACK_OK` when the command is accepted for execution
- `ACK_ERROR` when the command is rejected due to local/manual mode, hardware not ready, invalid parameter, or backend failure
- `detail` should carry backend-specific reason when useful

### `PUMP_SET_MAX_FLOW`
Purpose:
- configure the current maximum allowed pump flow envelope for the active backend

Rules:
- this is a configuration/control bound, not a direct run command
- it must be backend-independent at the interface level even if internal implementation differs

### `OP_STOP`
Purpose:
- explicit unconditional remote-controlled stop request

Rules:
- this is the canonical stop command
- host-side print logic should prefer `OP_STOP` over overloading `PUMP_SET_FLOW=0`
- node must apply the safest supported stop behavior for the backend
- stop behavior may be ramp stop, controlled stop, or immediate safe stop depending on hardware/backend policy

### `OP_RESET_FAULT`
Purpose:
- request fault reset when the backend supports it

Rules:
- acceptance depends on backend capability and current state
- unsupported backends should reject with normalized ACK semantics

## Manual / local override semantics

Manual or local override must be treated as a first-class control condition.

### Required behavior
If manual/local mode is active:
- remote flow/run commands must not be executed as normal run commands
- node must report rejection through ACK
- status must clearly show manual/local condition
- host layer must treat the pump as not remotely controllable until manual/local mode clears

### ACK behavior under manual/local override
Recommended normalized behavior:
- `status = ACK_ERROR`
- `err_code = ERR_BAD_STATE` or a dedicated future normalized code if added later
- `detail = backend-specific reason`
- pump fault/status model may also expose `FAULT_PUMP_MANUAL_MODE` where appropriate

### Status behavior under manual/local override
Manual/local state must be visible through the canonical status model using flags rather than backend-specific transport hacks:
- `PUMP_FLAG_MANUAL_MODE`
- `PUMP_FLAG_REMOTE_MODE`

Only one control authority should be considered active at a time.

## Layer responsibility matrix

### Pump node responsibilities
The pump node is responsible for:
- backend I/O
- hardware state validation
- manual/local input evaluation
- safe command application
- generation of canonical ACK
- generation of canonical `PumpStatus`

The pump node is not responsible for:
- print orchestration
- flush planning
- long host-side state machines
- UI policy

### Bridge responsibilities
The bridge is responsible for:
- host transport termination
- ESP-NOW forwarding
- retry / timeout handling
- exposing bridge-visible status to the host

The bridge is not responsible for:
- print business logic
- backend-specific pump policy
- flush or prime sequencing
- interpreting print intent

### Agent responsibilities
The agent is responsible for:
- print-linked pump orchestration
- synchronization with Klipper state
- flush / prime sequencing
- unconditional stop policy
- minimum-flow cutoff policy
- watchdog policy above transport level
- exposing a clean model to Moonraker / Mainsail

## Agent state machine goals

The host-side agent should evolve toward a small explicit state machine.

Suggested high-level states:
- `DISCONNECTED`
- `IDLE`
- `ARMED`
- `RUNNING`
- `FLUSHING`
- `STOPPING`
- `FAULT`
- `MANUAL_LOCKOUT`

Required transitions should cover:
- print start / print stop
- commanded flow becoming positive
- commanded flow dropping below minimum threshold
- manual/local override appearing or clearing
- communication loss
- backend fault
- unconditional emergency stop

The agent should become the only place where print-time business logic is coordinated.

## Immediate next milestone

The next design focus should be:
1. finalize minimal canonical pump semantics shared by VFD and TPL backends
2. define host-side state machine for print-linked pump control
3. integrate that model with Klipper, Moonraker, and Mainsail

The project should now prioritize system behavior over further transport-layer complexity.

## Minimal shared pump runtime model

The minimal shared runtime model must work for both:
- VFD / Modbus pump backend
- TPL / relay + analog backend

This means the canonical model must describe pump behavior, not driver internals.

### Canonical `PumpStatus` meaning

`PumpStatus` should represent only shared runtime state that higher layers need for orchestration.

Recommended shared fields:
- `StatusCommon c`
- `target_milli_lpm`
- `max_milli_lpm`
- `hw_setpoint_raw`
- `link_flags`
- `pump_flags`

### Meaning of shared fields

- `target_milli_lpm` = commanded target flow from the remote control layer
- real delivered flow is currently **not exposed as a canonical host-visible field** because there is no independent flow sensor yet
- `max_milli_lpm` = active configured upper limit
- `hw_setpoint_raw` = backend raw actuation value, exposed only as a generic debug/control field
- `link_flags` = communication and transport visibility flags
- `pump_flags` = logical runtime flags such as running, manual mode, remote mode, watchdog stop, hardware ready

### What belongs in `pump_flags`

`pump_flags` should carry shared logical conditions, for example:
- `PUMP_FLAG_RUNNING`
- `PUMP_FLAG_FORWARD`
- `PUMP_FLAG_REVERSE`
- `PUMP_FLAG_MANUAL_MODE`
- `PUMP_FLAG_REMOTE_MODE`
- `PUMP_FLAG_FAULT_LATCHED`
- `PUMP_FLAG_WDOG_STOP`
- `PUMP_FLAG_HW_READY`

### What does NOT belong in canonical `PumpStatus`

The canonical shared status should not directly depend on one backend family.

Examples that should not live in canonical `PumpStatus`:
- VFD output frequency
- VFD shaft speed
- VFD output current
- TPL-specific relay diagnostics
- TPL-specific potentiometer raw value
- backend-private hardware diagnostics

Those values may still exist, but they should be treated as backend diagnostics, not canonical pump state.

## Backend diagnostics rule

Backend-specific diagnostics are allowed, but they must be clearly separated from the shared control model.

Examples:
- VFD diagnostics:
  - actual frequency
  - motor speed
  - output current
  - raw drive fault register
- TPL diagnostics:
  - relay state
  - selector state
  - analog command value
  - backend-specific fault inputs

These diagnostics should not drive the project architecture.
They are secondary to the shared pump abstraction.

## Design consequence for next code changes

Before adding more fields or transport payloads, check them against this rule:

Question:
- does this field describe shared pump behavior needed by host orchestration?

If yes:
- it may belong in canonical `PumpStatus`

If no:
- it should stay backend-local or move into an optional diagnostics path later

## Printer deployment workflow

Canonical printer-side layout:

- repo: `/home/dan/drukmix`
- agent entrypoint: `/home/dan/drukmix/agent/drukmix_agent.py`
- live cfg: `/home/dan/printer_data/config/drukmix.cfg`
- live macros: `/home/dan/printer_data/config/drukmix_macros.cfg`
- systemd unit: `/etc/systemd/system/drukmix.service`

Deployment helper:

- `tools/drukmix`
- install to `/usr/local/bin/drukmix`
- normal update flow on printer:
  - `drukmix fetch`
  - `drukmix apply`
  - `drukmix klipper-restart`

During bring-up/debug printer-side changes may be captured back into repo:

- `drukmix capture`
- `drukmix publish "message"`

Rule:
- repo remains canonical source of truth
- `capture/publish` are allowed only as controlled debugging workflow, not as a second architecture

## VFD architecture and docs

### Where to look first

- `docs/vfd/README.md` — index: what document to open and when
- `docs/vfd/m900_m980_shared_semantics.md` — shared semantics for M900/M980
- `docs/vfd/m900_m980_differences.md` — series differences and capability boundary
- `docs/vfd/m900_m980_faults.md` — baseline fault map and recovery policy
- `docs/vfd/modbus_driver_contract.md` — contract between `pump_vfd`, `bridge`, `agent`, and future Klipper integration
- `config/vfd_profiles.yaml` — per-series profiles/capabilities

### Project rules for VFD fault handling

- Only communication-loss class faults are candidates for automatic recovery.
- All other VFD faults must remain operator-visible and should pause/hold the print flow until investigated.
- Fault recovery policy should live on the ESP / `pump_vfd` side, not in an external host service.
- `running` must not be interpreted as proof of physical shaft motion when commanded frequency is zero.
- Shared transport/status logic may be reused across M900 and M980, but series differences must stay in profiles/capabilities.

### Current implementation direction

1. Keep common Modbus transport and status model.
2. Move comm-loss recovery to ESP-side logic.
3. Preserve operator-handled behavior for all non-communication faults.
4. Validate real run behavior using different target speeds and observed status registers before deeper Klipper integration.


## Firmware

### Pump VFD baseline

Станом на зараз baseline для `firmware/pump_vfd` такий:

- Для поточного стенду з M980 підтверджений робочий `reset_fault()` path:
  - `REG_CMD_CONTROL (0x0002) = 6`  -> stop
  - `REG_CMD_CONTROL (0x0002) = 7`  -> reset fault
  - `REG_CMD_CONTROL (0x0002) = 6`  -> stop
- Тобто робочий baseline reset fault для цього стенду — саме `stop -> reset -> stop`.
- Спрощений варіант з одним write `0x0002 = 7` не вважати baseline для цього стенду, поки він не підтверджений окремим live тестом.
- Висновки про reset/fault логіку дозволено робити тільки після повного deployment sequence:
  - source change
  - `rm -rf firmware/pump_vfd/.pio` (коли є сумніви або мінялась fault/reset/debug логіка)
  - `cd firmware/pump_vfd && pio run`
  - `cd ../.. && ./tools/export_firmware.sh`
  - `./tools/flash_firmware.sh pump_vfd <port> <baud>`
  - live verification через monitor і команди з bridge
- Не змішувати monitor і direct host commands в один і той самий serial port pump node.
- Якщо `pio device monitor` відкритий на pump ESP, агентом у той самий `/dev/cu.usbserial-*` порт не ходити.

### Fixed checklist

Правило:
- не змінювати список довільно
- додавати тільки підтверджені пункти
- прибирати пункт тільки після явного підтвердження live-перевіркою

Список:
- [x] Знайдено робочий fault reset path для поточного M980: `stop -> reset -> stop` (live verified on hardware)
- [x] Підтверджено правильний deployment sequence для `pump_vfd`: `rebuild -> export -> flash -> live verify`
- [x] Уточнити правильну семантику `running` для M980; live-підтверджено: `running = (freq>0) or (speed!=0) or (current>0)`, а `RUN_STATE` не вважати ознакою фізичного руху
- [ ] Дочистити bridge ACK/retry semantics
- [x] Перевірити та прибрати дублювання reset command/retry path; live-підтверджено isolated test: один `OP_RESET_FAULT`, один ACK, без повторної resend-посилки
- [ ] Після стабілізації прибрати зайвий debug/test code
- [ ] Зробити clean architecture pass і прибрати застарілі/суперечливі baseline notes


### Verified M980 live behavior

### Verified bridge reset propagation

Підтверджено live end-to-end:

- isolated test виконувати тільки при зупиненому `drukmix.service`
- monitor на pump node показав один `OP_RESET_FAULT`
- `last_ack_seq` на bridge змінився рівно на один для reset-команди
- після `sleep 3` host-side `ping` показує:
  - `pump_fault_code = 0`
  - `pump_state = 3`
  - `pump_running = false`

Висновок:
- reset fault зараз підтверджений не тільки локально на `pump_vfd`, а й наскрізно через `bridge -> esp-now -> pump_vfd -> status back to host`
- для перевірки reset-path правильний тест тільки isolated:
  - `sudo systemctl stop drukmix.service`
  - `ping`
  - `reset-fault`
  - `sleep 3`
  - `ping`


Підтверджено live на стенді:

- До reset:
  - `fault=16`
  - `running=0`
  - `freq_x10=0`
  - `speed=0`
  - `current_x10=0`
- Робочий reset sequence:
  - `0x0002 = 6`
  - `0x0002 = 7`
  - `0x0002 = 6`
- Після reset:
  - `fault=0`
  - `running=0`
  - `freq_x10=0`
  - `speed=0`
  - `current_x10=0`

Висновок:
- для M980 `RUN_STATE (0x1000)` не використовувати як ознаку фізичного руху
- для DrukMix `running` рахувати від фактичних telemetry-полів:
  - `actual_freq_x10 > 0`
  - або `actual_speed_raw != 0`
  - або `output_current_x10 > 0`

### Bridge baseline

- `firmware/bridge` зараз не чіпаємо без окремої причини.
- Поточна проблема локалізована в `pump_vfd`, не в bridge.


## Agent architecture findings and refactor boundary

Поточний `drukmix_agent.py` фактично змішує 4 різні шари в одному файлі:

1. TPL-specific semantics
2. host orchestration
3. Moonraker integration
4. bridge transport

Це означає, що current agent зараз не є чистим універсальним orchestration layer.
У ньому одночасно живуть:
- логіка друку і синхронізації потоку
- старі TPL-специфічні правила
- Moonraker websocket / remote methods
- USB framing / bridge transport details

### Main architectural risk

Головний ризик подальших змін:
- адаптувати agent під VFD / dmbus
- але залишити старі TPL-specific механіки всередині того ж шару
- і далі компенсувати різницю новими умовами та хакaми

Це створить важкий змішаний host-side код, який:
- складно підтримувати
- складно дебажити
- може створювати зайве навантаження на CB1 / host system
- погано масштабується на нові device types

### Confirmed current agent layering

#### 1. TPL-specific semantics
У current agent присутні TPL-oriented маркери та логіка, які не можна вважати generic host abstraction:

- `EF_MANUAL_FWD`
- `EF_MANUAL_REV`
- `EF_AUTO_ALLOWED`
- `EF_AUTO_ACTIVE`
- `EF_DIR_ASSERTED`
- `EF_WIPER_TPL`
- `decode_mode()`
- `expected_code()`
- `confirm_applied()`

Висновок:
- ці частини не повинні залишатися всередині generic agent core
- їх треба або винести в окремий TPL-specific compatibility layer, або зберегти лише як legacy reference

#### 2. Host orchestration
У current agent already lives valid host-side orchestration logic:

- print-state-dependent pumping
- flow-from-motion logic через `live_extruder_velocity`
- `flow_gain`
- `retract_deadband_mm_s`
- `retract_gain`
- `min_run_lpm`
- `min_run_hold_s`
- `drukmix_flush`
- `drukmix_flush_stop`
- pause policy:
  - `pause_on_pump_offline`
  - `pause_on_manual_during_print`
- `pause_with_popup()`

Висновок:
- саме цей шар і є правильною відповідальністю host agent
- його не треба пхати в bridge або в device node
- але його треба відокремити від transport/details/backend-specific logic

#### 3. Moonraker integration
У current agent є окремий Moonraker-facing шар:

- `MoonrakerClient`
- `connection.register_remote_method`
- `printer.objects.subscribe`
- `notify_status_update`
- `printer.print.pause`
- `RESPOND TYPE=...`

Висновок:
- це окремий integration layer
- він не повинен бути змішаний з bus/device semantics
- він має адаптувати Moonraker state до internal host model, а не нести backend-specific control logic

#### 4. Bridge transport
У current agent є окремий transport/glue layer:

- `BridgeSerial`
- `build_usb_packet()`
- `parse_bridge_status()`
- `USB_SET_FLOW`
- `USB_SET_MAXLPM`
- `USB_BRIDGE_STATUS`

Висновок:
- packet framing / COBS / CRC / bridge serial transport не повинні змішуватися з orchestration core
- transport треба тримати окремим адаптером

## Preserved TPL legacy snapshot

Щоб не втратити стару TPL host logic перед refactor, у repo збережено окремий archival snapshot:

- `agent/legacy_tlp/drukmix_agent_tlp_legacy.py`
- `agent/legacy_tlp/drukmix_cfg_tlp_legacy.cfg`
- `agent/legacy_tlp/drukmix_macros_tlp_legacy.cfg`
- `docs/agent/tpl_legacy_snapshot.md`

Правило:
- цей snapshot є reference-only
- його не refactor'ити inplace
- він збережений як джерело поведінкової семантики TPL для майбутньої інтеграції

## Current agent gaps already identified

У current `drukmix_agent.py` already видно розрив між macro/API surface та реальною реалізацією.

Поточні gaps:

- `drukmix_set_limits` відсутній
- `drukmix_clear_overrides` відсутній
- `USB_RESET_FAULT` відсутній
- `reset_fault` path відсутній

Висновок:
- current agent уже не повністю узгоджений з macros/config expectations
- не можна безконтрольно нашаровувати нові можливості поверх цього стану
- спочатку потрібне чітке розділення шарів

## DMBus scope rule

`dmbus v1` is the current canonical baseline for device communication.

Його мета:

- common command transport
- common ACK semantics
- common device status model
- common node-to-host abstraction

`dmbus v1` is not required to encode the entire product workflow.

Higher-level behavior may still live above the bus, for example:

- FLUSH orchestration
- pause policy on faults
- unconditional stop policy
- override persistence
- print-state-dependent actions

If `dmbus v1` later proves insufficient for stable multi-device orchestration:

- introducing `dmbus v2` is allowed
- but only after stabilizing the current `v1` baseline
- do not compensate protocol gaps with uncontrolled Python-side hacks

## Moonraker / Mainsail integration rule

Long-term integration must not stop at macro buttons only.

Target direction:

- pump state should be exposed as structured device/status data through Moonraker-facing integration
- Mainsail should be able to render pump/device tiles from structured state, not only from ad-hoc macros
- macros remain valid for operator actions, but must not be the only UI/control surface

## Multi-device scaling rule

This project is expected to grow beyond one pump backend.

Future devices may include:

- mixers
- feeders / unloaders
- silos
- pressure sensors
- temperature / humidity sensors
- RPM / rotation feedback devices

Therefore:

- current architecture must scale to multiple external ESP32-based device nodes
- shared bus and shared host abstractions are needed not only for VFD vs TPL, but for the future device family as a whole
- avoid host-side designs that assume only one permanent pump-specific path

## Host vs ESP responsibility rule

Maximum reasonable low-level logic should be moved out of the host and into external ESP32 device nodes.

### Device node should own:
- hardware I/O
- backend-specific actuation
- local safety handling
- local/manual input handling
- backend-specific diagnostics
- canonical ACK generation
- canonical STATUS generation

### Bridge should own:
- transport only
- forwarding
- retry / timeout
- compact host-visible status transport

### Host agent should own:
- print orchestration
- motion-to-flow mapping
- FLUSH / PRIME sequencing
- pause / hold policy
- override lifecycle
- Moonraker / Mainsail integration
- multi-device coordination at workflow level

Висновок:
- current architectural direction with external ESP32 nodes is correct
- host should become lighter, not heavier
- CB1-side logic should stay orchestration-oriented, not hardware-protocol-heavy

## Current refactor boundary

До тих пір, поки насос не буде синхронно крутитися на реальному принтері під час запуску файлу, не робити "cleanups for beauty".

Поточний дозволений refactor boundary:

1. preserve legacy behavior references
2. separate current agent into clearer layers
3. avoid losing TPL behavior knowledge
4. do not add uncontrolled compatibility hacks
5. do not redesign protocol prematurely before live synchronized printing works

## Refactor order rule

Перші 3 напрямки відділення в agent мають бути саме такі:

### Step 1 — isolate TPL-specific semantics
Перше, що треба відділити:
- TPL-specific flags
- TPL-specific mode decoding
- TPL-specific applied-code/confirm semantics

### Step 2 — isolate bridge transport
Далі треба відділити:
- USB framing
- COBS/CRC packet handling
- bridge serial transport API

### Step 3 — isolate Moonraker adapter
Далі треба відділити:
- websocket RPC
- remote methods
- object subscriptions
- UI/respond/pause bridge to Moonraker

Після цього вже можна чисто формувати:

- generic host orchestration core
- TPL compatibility layer
- VFD/dmbus path
- future multi-device integrations

## Current working conclusion

Поточний вибір напряму вважається правильним:

- `dmbus` варто продовжувати
- максимум low-level logic варто виносити на ESP32
- host agent має залишатися orchestration layer
- TPL legacy behavior треба зберегти як reference
- refactor має бути контрольований, без втрати поточної працездатності та без "костиль за костилем"


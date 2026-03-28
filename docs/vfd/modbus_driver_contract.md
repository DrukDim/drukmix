# VFD Modbus driver contract

## Supported series
- M900
- M980

## Purpose

Цей файл описує контракт між:
- `firmware/pump_vfd`
- `firmware/bridge`
- `drukmix_driver.py`
- Klipper / Moonraker / service integration

## Shared assumptions

- control path = RS485 / Modbus RTU
- VFD configured for communication control
- status polling based on common monitor registers
- reset fault policy відділена від normal run policy

## Required runtime state

Driver / node / host side мають розрізняти:

- `fault_code`
- `logical_running`
- `actual_freq_x10`
- `actual_speed_raw`
- `output_current_x10`
- `target_milli_lpm`
- `cmd_setpoint_raw`
- `comm_ok`
- `series_profile`

## Rules

### Rule 1
Не трактувати `logical_running` як еквівалент "мотор фізично крутиться".

### Rule 2
Після `reset_fault()` обов'язково перечитати status register-и.

### Rule 3
Auto-recovery дозволяти тільки для communication-loss class.

### Rule 4
Recovery policy має жити максимально близько до pump/VFD side, а не в зовнішньому сервісі.

### Rule 5
Host/driver/bridge повинні бачити нормалізований стан, а не вгадувати серію VFD по непрямих ознаках.

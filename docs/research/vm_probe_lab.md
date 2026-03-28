# VM Probe Lab (Klipper + Moonraker + fake bridge)

This lab path is intended to validate prestart/prestop timing end-to-end without real pump hardware.

Goals:
- keep production host logic unchanged;
- run real `drukmix_driver.py`, real backends, and real `drukmix_planner_probe.py`;
- emulate only the bridge/device boundary through a PTY fake bridge.

## Canonical constraints

- Host runtime settings are owned by `drukmix_driver.cfg`.
- Controller policy settings are owned by `drukmix_controller.cfg`.
- Do not reintroduce `drukmix_planner.cfg` as a settings source unless explicitly requested.
- Probe section in `printer.cfg` is managed by `tools/drukmix`.

## Lab architecture

Flow under test:

`G-code -> Klipper lookahead -> drukmix_planner_probe -> drukmix_controller -> Moonraker status -> drukmix_driver -> bridge_usb_transport -> fake_bridge_pty -> fake pump model`

What is real:
- Klipper planner and extruder move path
- probe status calculation
- Moonraker API/status transport
- DrukMix orchestration and backend logic

What is simulated:
- USB bridge transport endpoint
- pump status dynamics and faults

## Setup steps (VM)

1. Ensure Klipper and Moonraker are active.
2. Clone repo in VM and checkout debug branch.
3. Install planner/controller extras from repo into Klipper extras path.
4. Keep DrukMix driver config in `~/printer_data/config/drukmix_driver.cfg`.
5. Keep DrukMix controller config in `~/printer_data/config/drukmix_controller.cfg`.
6. Configure driver `serial_port` to the PTY path exported by fake bridge emulator.

## Fake bridge usage

Run emulator in VM:

```bash
cd ~/work/drukmix
python3 tools/lab/fake_bridge_pty.py --write-tty-path /tmp/drukmix_fake_bridge.tty --log-jsonl /tmp/fake_bridge.jsonl --verbose
```

The script prints slave PTY path and also writes it into `/tmp/drukmix_fake_bridge.tty`.

Use it in DrukMix driver config:

```ini
[drukmix_driver]
serial_port = /dev/pts/X
backend = pumpvfd
```

Where `/dev/pts/X` is the path from `/tmp/drukmix_fake_bridge.tty`.

## Minimal run sequence

1. Start fake bridge emulator.
2. Point `drukmix_driver.cfg` `serial_port` to PTY path.
3. Run `./tools/drukmix update` (or restart driver service).
4. Restart Klipper and Moonraker if probe config changed.
5. Start test print/G-code scenario.
6. Collect logs from:
   - `~/printer_data/logs/klippy.log`
   - `~/printer_data/logs/drukmix_driver.log`
   - `/tmp/fake_bridge.jsonl`

## Metrics to inspect

Probe side:
- `queue_tail_s`
- `time_to_print_start_s`
- `time_to_print_stop_s`
- `time_to_print_start_source`
- `control_velocity_mms`

Controller/driver side:
- controller state (`idle`, `prestart`, `run`, `prestop`, `blocked`)
- controller `target_pct`

Bridge side:
- `set_flow` events
- target/applied dynamics
- link/mode/fault responses

## Acceptance examples

With `pump_start_lookahead_s = 4.0`:
- controller should enter `prestart` before first print window;
- prestart lead should be stable and measurable;
- `prestop` should taper output without early hard stop.

Safety:
- mode/fault/offline must override planner prestart.

# TPL legacy host logic snapshot

Source snapshot:
- file: `drukmix_agent.py`
- purpose: preserve pre-refactor host logic that was built around TPL behavior, overrides, flush workflow, and Moonraker remote methods

## Important preserved areas
- `EF_MANUAL_FWD`
- `EF_MANUAL_REV`
- `EF_AUTO_ALLOWED`
- `EF_AUTO_ACTIVE`
- `EF_DIR_ASSERTED`
- `EF_WIPER_TPL`
- `decode_mode`
- `drukmix_flush`
- `drukmix_flush_stop`
- `drukmix_set_gain`
- `drukmix_set_debug`
- `drukmix_reload_cfg`
- `confirm_applied`
- `expected_code`
- `live_extruder_velocity`
- `min_run_hold_s`
- `pause_on_pump_offline`
- `pause_on_manual_during_print`

## Notes
- This snapshot is archival/reference only.
- Do not refactor this file in place.
- New cleanup should happen in current working agent, with this copy kept as behavior reference for future TPL integration.

# Hardware-free virtual extruder for lab/VM testing.
#
# Provides a minimal extruder interface that satisfies:
#   - drukmix_planner_probe (hooks process_move)
#   - Klipper toolhead E-axis move processing (no "Extrude when no extruder" error)
#
# Does NOT require any real hardware: no heater_pin, no sensor_pin, no stepper.
# Intended for use on lab hosts with no physical MCU attached (e.g. Linux-only QEMU VM).
#
# Usage in printer.cfg:
#   [drukmix_virtual_extruder]
#   # no parameters required

import logging


class DrukMixVirtualExtruder:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = 'extruder'

        # Register as 'extruder' so printer.lookup_object('extruder') finds us.
        # DrukMixPlannerProbe and Moonraker status use this path.
        self.printer.add_object('extruder', self)

        # Register with the toolhead to replace DummyExtruder in extra_axes[0].
        # This allows E-axis moves to pass through without the
        # "Extrude when no extruder present" error.
        toolhead = self.printer.lookup_object('toolhead', None)
        if toolhead is not None:
            toolhead.set_extruder(self, 0.)
            logging.info("drukmix_virtual_extruder: registered with toolhead")
        else:
            self.printer.register_event_handler(
                "klippy:connect", self._handle_connect)

    def _handle_connect(self):
        toolhead = self.printer.lookup_object('toolhead', None)
        if toolhead is not None:
            toolhead.set_extruder(self, 0.)
            logging.info("drukmix_virtual_extruder: registered with toolhead (deferred)")

    # --- Extruder interface required by toolhead ---

    def get_name(self):
        return self.name

    def get_axis_gcode_id(self):
        return 'E'

    def get_heater(self):
        raise self.printer.command_error(
            "drukmix_virtual_extruder: no heater (virtual extruder, lab only)")

    def get_trapq(self):
        # No hardware trapq. E-axis position is not tracked in MCU step generation.
        return None

    def check_move(self, move, ea_index):
        # Allow all E-axis moves unconditionally.
        pass

    def calc_junction(self, prev_move, move, ea_index):
        return move.max_cruise_v2

    def process_move(self, print_time, move, ea_index):
        # No-op: drukmix_planner_probe wraps this method to observe move data.
        pass

    def find_past_position(self, print_time):
        return 0.

    def get_status(self, eventtime):
        return {
            'temperature': 0.0,
            'target': 0.0,
            'power': 0.0,
            'can_extrude': True,
        }


def load_config(config):
    return DrukMixVirtualExtruder(config)

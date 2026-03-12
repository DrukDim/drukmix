# Experimental Klipper extra for DrukMix planner research.
#
# Purpose:
# - expose planner-oriented extruder signals for research
# - keep runtime impact low
# - avoid changing actual print behavior
#
# This file is intentionally minimal and instrumentation-only.

import logging

class DrukMixPlannerProbe:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.toolhead = None
        self.mcu = None
        self.motion_report = None
        self.extruder_name = config.get('extruder', 'extruder')
        self.status = {
            'available': False,
            'extruder': self.extruder_name,
            'planner_lead_s': None,
            'planned_extruder_velocity': None,
            'planned_extruder_position': None,
            'live_position_source': None,
        }
        self.printer.register_event_handler("klippy:connect", self._handle_connect)

    def _handle_connect(self):
        try:
            self.toolhead = self.printer.lookup_object('toolhead')
        except Exception:
            self.toolhead = None
        try:
            self.motion_report = self.printer.lookup_object('motion_report', None)
        except Exception:
            self.motion_report = None
        try:
            mcu = self.printer.lookup_object('mcu', None)
            if mcu is None:
                mcu = self.printer.lookup_object('mcu ' + self.printer.get_start_args().get('mcu', ''), None)
            self.mcu = mcu
        except Exception:
            self.mcu = None
        self.status['available'] = bool(self.toolhead is not None)
        logging.info("drukmix_planner_probe connected: extruder=%s available=%s",
                     self.extruder_name, self.status['available'])

    def _get_estimated_print_time(self, eventtime):
        if self.mcu is None:
            return None
        try:
            return self.mcu.estimated_print_time(eventtime)
        except Exception:
            return None

    def _get_extruder_trapq_state(self, print_time):
        if self.motion_report is None:
            return (None, None)
        try:
            dtrapq = self.motion_report.dtrapqs.get(self.extruder_name)
            if dtrapq is None:
                return (None, None)
            pos, vel = dtrapq.get_trapq_position(print_time)
            return (pos, vel)
        except Exception:
            return (None, None)

    def get_status(self, eventtime):
        print_time = None
        planner_lead = None
        planned_pos = None
        planned_vel = None

        if self.toolhead is not None:
            try:
                print_time = self.toolhead.get_last_move_time()
            except Exception:
                print_time = None

        est_print_time = self._get_estimated_print_time(eventtime)
        if print_time is not None and est_print_time is not None:
            planner_lead = max(0.0, float(print_time) - float(est_print_time))

        if print_time is not None:
            planned_pos, planned_vel = self._get_extruder_trapq_state(print_time)

        self.status.update({
            'available': bool(self.toolhead is not None),
            'extruder': self.extruder_name,
            'planner_lead_s': planner_lead,
            'planned_extruder_velocity': planned_vel,
            'planned_extruder_position': planned_pos,
            'live_position_source': 'trapq',
        })
        return dict(self.status)

def load_config(config):
    return DrukMixPlannerProbe(config)

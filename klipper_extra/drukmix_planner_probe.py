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
        self.toolhead = None
        self.motion_report = None
        self.mcu = None
        self.extruder_name = config.get('extruder', 'extruder')
        self.lookahead_points = [0.0, 0.25, 0.5, 1.0]
        self.status = {
            'available': False,
            'extruder': self.extruder_name,
            'estimated_print_time': None,
            'queue_end_print_time': None,
            'queue_tail_s': None,
            'planned_pos_now': None,
            'planned_v_now': None,
            'planned_pos_250ms': None,
            'planned_v_250ms': None,
            'planned_pos_500ms': None,
            'planned_v_500ms': None,
            'planned_pos_1000ms': None,
            'planned_v_1000ms': None,
            'data_source': 'trapq',
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
            self.mcu = self.printer.lookup_object('mcu', None)
        except Exception:
            self.mcu = None

        logging.info(
            "drukmix_planner_probe connected: extruder=%s available=%s",
            self.extruder_name,
            bool(self.toolhead is not None and self.motion_report is not None),
        )

    def _get_estimated_print_time(self, eventtime):
        if self.mcu is None:
            return None
        try:
            return float(self.mcu.estimated_print_time(eventtime))
        except Exception:
            return None

    def _get_queue_end_print_time(self):
        if self.toolhead is None:
            return None
        try:
            return float(self.toolhead.get_last_move_time())
        except Exception:
            return None

    def _get_trapq_point(self, print_time):
        if self.motion_report is None or print_time is None:
            return (None, None)
        try:
            dtrapq = self.motion_report.dtrapqs.get(self.extruder_name)
            if dtrapq is None:
                return (None, None)
            pos, vel = dtrapq.get_trapq_position(print_time)
            return (float(pos), float(vel))
        except Exception:
            return (None, None)

    def get_status(self, eventtime):
        est_print_time = self._get_estimated_print_time(eventtime)
        queue_end_print_time = self._get_queue_end_print_time()

        queue_tail_s = None
        if est_print_time is not None and queue_end_print_time is not None:
            queue_tail_s = max(0.0, queue_end_print_time - est_print_time)

        samples = {}
        if est_print_time is not None:
            for dt in self.lookahead_points:
                pos, vel = self._get_trapq_point(est_print_time + dt)
                samples[dt] = (pos, vel)
        else:
            for dt in self.lookahead_points:
                samples[dt] = (None, None)

        self.status.update({
            'available': bool(self.toolhead is not None and self.motion_report is not None),
            'extruder': self.extruder_name,
            'estimated_print_time': est_print_time,
            'queue_end_print_time': queue_end_print_time,
            'queue_tail_s': queue_tail_s,
            'planned_pos_now': samples[0.0][0],
            'planned_v_now': samples[0.0][1],
            'planned_pos_250ms': samples[0.25][0],
            'planned_v_250ms': samples[0.25][1],
            'planned_pos_500ms': samples[0.5][0],
            'planned_v_500ms': samples[0.5][1],
            'planned_pos_1000ms': samples[1.0][0],
            'planned_v_1000ms': samples[1.0][1],
            'data_source': 'trapq',
        })
        return dict(self.status)


def load_config(config):
    return DrukMixPlannerProbe(config)

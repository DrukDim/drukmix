# Experimental Klipper extra for DrukMix planner research.
#
# Purpose:
# - expose planner-oriented extruder signals for research
# - keep runtime impact low
# - avoid changing actual print behavior
#
# Production approach in this version:
# - mirror extruder moves at enqueue time via PrinterExtruder.process_move()
# - expose compact planner-authoritative host control signals
#
# This file is part of the production planner signal path.

import logging
from collections import deque

KEEP_HISTORY_S = 5.0


class DrukMixPlannerProbe:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.toolhead = None
        self.mcu = None
        self.extruder_name = config.get('extruder', 'extruder')
        self.extruder_obj = None
        self._orig_process_move = None
        self._moves = deque()
        self.debug_enabled = config.getboolean('debug_enabled', False)
        self.debug_every_n_moves = config.getint('debug_every_n_moves', 200)
        self._debug_move_counter = 0
        self.print_velocity_epsilon = config.getfloat('print_velocity_epsilon', 0.001, minval=0.0)
        self.pump_start_lookahead_s = config.getfloat('pump_start_lookahead_s', 3.0, minval=0.0)
        self.pump_stop_lookahead_s = config.getfloat('pump_stop_lookahead_s', 3.0, minval=0.0)
        self.status = {
            'available': False,
            'extruder': self.extruder_name,
            'estimated_print_time': None,
            'queue_end_print_time': None,
            'queue_tail_s': None,
            'data_source': 'enqueue_mirror',
            'print_window_active': False,
            'time_to_print_start_s': None,
            'time_to_print_stop_s': None,
            'control_velocity_mms': 0.0,
        }
        self.printer.register_event_handler("klippy:connect", self._handle_connect)

    def _handle_connect(self):
        self.toolhead = self.printer.lookup_object('toolhead', None)
        self.mcu = self.printer.lookup_object('mcu', None)
        self.extruder_obj = self.printer.lookup_object(self.extruder_name, None)
        self._install_hook()
        self.status['available'] = bool(
            self.toolhead is not None
            and self.mcu is not None
            and self.extruder_obj is not None
            and self._orig_process_move is not None
        )
        logging.info(
            "drukmix_planner_probe connected: extruder=%s available=%s hooked=%s",
            self.extruder_name,
            self.status['available'],
            self._orig_process_move is not None,
        )

    def _install_hook(self):
        if self.extruder_obj is None:
            return
        if self._orig_process_move is not None:
            return

        orig = self.extruder_obj.process_move
        probe = self

        def wrapped_process_move(print_time, move, ea_index):
            axis_r = move.axes_r[ea_index]
            accel = move.accel * axis_r
            start_v = move.start_v * axis_r
            cruise_v = move.cruise_v * axis_r
            total_t = move.accel_t + move.cruise_t + move.decel_t
            end_time = print_time + total_t

            probe._moves.append({
                'start_time': float(print_time),
                'end_time': float(end_time),
                'accel_t': float(move.accel_t),
                'cruise_t': float(move.cruise_t),
                'decel_t': float(move.decel_t),
                'start_v': float(start_v),
                'cruise_v': float(cruise_v),
                'accel': float(accel),
                'start_pos': float(move.start_pos[ea_index]),
                'axis_r': float(axis_r),
                'can_pressure_advance': bool(
                    axis_r > 0.0 and (move.axes_d[0] or move.axes_d[1])
                ),
            })
            probe._debug_move_counter += 1
            if probe.debug_enabled:
                if probe._debug_move_counter <= 5 or (probe._debug_move_counter % max(1, probe.debug_every_n_moves)) == 0:
                    logging.info(
                        "drukmix_planner_probe move: n=%d pt=%.6f ea=%s axis_r=%.6f start_v=%.6f cruise_v=%.6f accel_t=%.6f cruise_t=%.6f decel_t=%.6f end=%.6f",
                        probe._debug_move_counter,
                        float(print_time),
                        ea_index,
                        float(axis_r),
                        float(start_v),
                        float(cruise_v),
                        float(move.accel_t),
                        float(move.cruise_t),
                        float(move.decel_t),
                        float(end_time),
                    )
            return orig(print_time, move, ea_index)

        self.extruder_obj.process_move = wrapped_process_move
        self._orig_process_move = orig

    def _estimated_print_time(self, eventtime):
        if self.mcu is None:
            return None
        try:
            return float(self.mcu.estimated_print_time(eventtime))
        except Exception:
            return None

    def _prune(self, est_print_time):
        if est_print_time is None:
            return
        cutoff = est_print_time - KEEP_HISTORY_S
        while self._moves and self._moves[0]['end_time'] < cutoff:
            self._moves.popleft()

    def _find_move_at(self, t):
        for m in self._moves:
            if m['start_time'] <= t <= m['end_time']:
                return m
        return None

    def _velocity_in_move(self, m, t):
        dt = t - m['start_time']
        if dt < 0.0 or dt > (m['accel_t'] + m['cruise_t'] + m['decel_t']):
            return None

        accel_t = m['accel_t']
        cruise_t = m['cruise_t']
        decel_t = m['decel_t']
        start_v = m['start_v']
        cruise_v = m['cruise_v']
        accel = m['accel']

        if dt <= accel_t:
            return start_v + accel * dt

        dt -= accel_t
        if dt <= cruise_t:
            return cruise_v

        dt -= cruise_t
        if dt <= decel_t:
            return cruise_v - accel * dt

        return None

    def _is_print_move(self, m):
        if m is None:
            return False
        if m['end_time'] <= m['start_time']:
            return False
        if m.get('axis_r', 0.0) <= 0.0:
            return False
        if max(abs(m.get('start_v', 0.0)), abs(m.get('cruise_v', 0.0))) <= self.print_velocity_epsilon:
            return False
        return True

    def _first_print_move_after(self, est):
        if est is None:
            return None
        for m in self._moves:
            if not self._is_print_move(m):
                continue
            if m['end_time'] < est:
                continue
            return m
        return None

    def _last_print_move_after(self, est):
        if est is None:
            return None
        for m in reversed(self._moves):
            if not self._is_print_move(m):
                continue
            if m['end_time'] < est:
                continue
            return m
        return None

    def get_status(self, eventtime):
        est = self._estimated_print_time(eventtime)
        self._prune(est)

        queue_end = self._moves[-1]['end_time'] if self._moves else est
        tail = None
        if est is not None and queue_end is not None:
            tail = max(0.0, float(queue_end) - float(est))

        first_print = self._first_print_move_after(est)
        last_print = self._last_print_move_after(est)

        time_to_print_start_s = None
        if est is not None and first_print is not None:
            time_to_print_start_s = max(0.0, float(first_print['start_time']) - float(est))

        time_to_print_stop_s = None
        if est is not None and last_print is not None:
            time_to_print_stop_s = max(0.0, float(last_print['end_time']) - float(est))

        print_window_active = last_print is not None

        control_velocity_mms = 0.0
        if est is not None:
            active_move = self._find_move_at(est)
            if self._is_print_move(active_move):
                v = self._velocity_in_move(active_move, est)
                if v is not None:
                    control_velocity_mms = max(0.0, float(v))
            elif (
                first_print is not None
                and time_to_print_start_s is not None
                and time_to_print_start_s <= self.pump_start_lookahead_s
            ):
                sample_t = min(
                    first_print['end_time'],
                    first_print['start_time'] + 0.05
                )
                v = self._velocity_in_move(first_print, sample_t)
                if v is not None:
                    control_velocity_mms = max(0.0, float(v))

        out = {
            'available': self.status['available'],
            'extruder': self.extruder_name,
            'estimated_print_time': est,
            'queue_end_print_time': queue_end,
            'queue_tail_s': tail,
            'data_source': 'enqueue_mirror',
            'print_window_active': bool(print_window_active),
            'time_to_print_start_s': time_to_print_start_s,
            'time_to_print_stop_s': time_to_print_stop_s,
            'control_velocity_mms': control_velocity_mms,
        }

        self.status.update(out)
        if self.debug_enabled:
            first = self._moves[0]['start_time'] if self._moves else None
            last = self._moves[-1]['end_time'] if self._moves else None
            logging.info(
                "drukmix_planner_probe status: est=%s moves=%d first=%s last=%s queue_end=%s tail=%s start_lookahead=%.3f stop_lookahead=%.3f t_start=%s t_stop=%s control_velocity=%s",
                est,
                len(self._moves),
                first,
                last,
                queue_end,
                tail,
                self.pump_start_lookahead_s,
                self.pump_stop_lookahead_s,
                time_to_print_start_s,
                time_to_print_stop_s,
                control_velocity_mms,
            )
        return dict(self.status)


def load_config(config):
    return DrukMixPlannerProbe(config)

# Production Klipper extra for DrukMix planner-authoritative pump control.
#
# Source of truth:
# - mirror extruder moves at enqueue time via PrinterExtruder.process_move()
# - expose compact planner-authoritative signals for:
#   - prestart
#   - online synchronization
#   - prestop
#
# This file must not read raw trapq buffers.

import logging
import importlib
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
        self.extruder_axis_index = 3
        self._orig_process_move = None
        self._moves = deque()

        self.debug_enabled = config.getboolean('debug_enabled', False)
        self.debug_every_n_moves = config.getint('debug_every_n_moves', 200)
        self._debug_move_counter = 0

        self.print_velocity_epsilon = config.getfloat(
            'print_velocity_epsilon', 0.001, minval=0.0
        )
        self.print_gap_merge_s = config.getfloat(
            'print_gap_merge_s', 0.75, minval=0.0
        )
        # Optional: raise host-side lookahead buffer target so planned horizon
        # can extend beyond the default ~1s behavior when explicitly requested.
        self.host_buffer_target_s = config.getfloat(
            'host_buffer_target_s', 0.0, minval=0.0, maxval=30.0
        )

        self.status = {
            'available': False,
            'estimated_print_time': None,
            'queue_tail_s': None,
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
        self._resolve_extruder_axis_index()
        self._apply_host_buffer_target()

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

    def _resolve_extruder_axis_index(self):
        self.extruder_axis_index = 3
        if self.toolhead is None:
            return
        try:
            extra_axes = list(getattr(self.toolhead, 'extra_axes', []) or [])
        except Exception:
            return

        for i, ea in enumerate(extra_axes):
            if ea is None:
                continue
            try:
                name = ea.get_name()
            except Exception:
                name = None
            if name == self.extruder_name:
                self.extruder_axis_index = 3 + i
                return

    def _apply_host_buffer_target(self):
        target = max(0.0, float(self.host_buffer_target_s))
        if target <= 0.0 or self.toolhead is None:
            return

        try:
            toolhead_mod = importlib.import_module('toolhead')

            prev_high = float(getattr(toolhead_mod, 'BUFFER_TIME_HIGH', 1.0))
            prev_start = float(getattr(toolhead_mod, 'BUFFER_TIME_START', 0.25))

            toolhead_mod.BUFFER_TIME_HIGH = target
            if prev_start >= target:
                toolhead_mod.BUFFER_TIME_START = max(0.05, target * 0.25)

            lookahead = getattr(self.toolhead, 'lookahead', None)
            if lookahead is not None:
                lookahead.set_flush_time(target)

            logging.warning(
                "drukmix_planner_probe host buffer target applied: high %.3f -> %.3f (start %.3f)",
                prev_high,
                target,
                float(getattr(toolhead_mod, 'BUFFER_TIME_START', prev_start)),
            )
        except Exception:
            logging.exception(
                "drukmix_planner_probe failed to apply host_buffer_target_s=%.3f",
                target,
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
                'axis_r': float(axis_r),
            })

            probe._debug_move_counter += 1
            if probe.debug_enabled:
                if (
                    probe._debug_move_counter <= 5
                    or (probe._debug_move_counter % max(1, probe.debug_every_n_moves)) == 0
                ):
                    logging.info(
                        "drukmix_planner_probe move: n=%d pt=%.6f ea=%s start_v=%.6f cruise_v=%.6f accel=%.6f accel_t=%.6f cruise_t=%.6f decel_t=%.6f end=%.6f",
                        probe._debug_move_counter,
                        float(print_time),
                        ea_index,
                        float(start_v),
                        float(cruise_v),
                        float(accel),
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
        total_t = m['accel_t'] + m['cruise_t'] + m['decel_t']
        if dt < 0.0 or dt > total_t:
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
        return True

    def _first_print_move_after(self, est):
        if est is None:
            return None
        for m in self._moves:
            if not self._is_print_move(m):
                continue
            # Future-start candidate for prestart; do not reuse already-started moves.
            if m['start_time'] < est:
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

    def _print_window_from_move(self, seed_move):
        if seed_move is None or not self._is_print_move(seed_move):
            return None, None

        # Merge short non-print interruptions (travel/micro-pauses) into one
        # logical print window so host control does not thrash prestart/prestop.
        gap_tolerance_s = max(0.0, float(self.print_gap_merge_s))
        first_move = seed_move
        last_move = seed_move
        in_window = False

        for m in self._moves:
            if m is seed_move:
                in_window = True
                continue
            if not in_window or not self._is_print_move(m):
                continue
            if m['start_time'] > (last_move['end_time'] + gap_tolerance_s):
                break
            if m['end_time'] > last_move['end_time']:
                last_move = m

        return first_move, last_move

    def _next_print_window_after(self, t_after):
        if t_after is None:
            return None, None

        gap_tolerance_s = max(0.0, float(self.print_gap_merge_s))
        for m in self._moves:
            if not self._is_print_move(m):
                continue
            if m['start_time'] <= (float(t_after) + gap_tolerance_s):
                continue
            return self._print_window_from_move(m)
        return None, None

    def _pending_lookahead_print_window(self, est):
        if est is None or self.toolhead is None:
            return None, None, None

        lookahead = getattr(self.toolhead, 'lookahead', None)
        queue = getattr(lookahead, 'queue', None)
        if not queue:
            return None, None, None

        committed_tail = float(self._moves[-1]['end_time']) if self._moves else float(est)
        try:
            t_cursor = max(
                float(est),
                float(getattr(self.toolhead, 'print_time', est)),
                committed_tail,
            )
        except Exception:
            t_cursor = float(est)

        gap_tolerance_s = max(0.0, float(self.print_gap_merge_s))
        window_start = None
        window_end = None
        pending_tail = None

        for mv in queue:
            try:
                seg_t = float(mv.accel_t) + float(mv.cruise_t) + float(mv.decel_t)
            except Exception:
                continue
            if seg_t <= 0.0:
                continue

            m_start = t_cursor
            m_end = t_cursor + seg_t
            t_cursor = m_end
            pending_tail = m_end

            axis_r = 0.0
            try:
                axis_r = float(mv.axes_r[self.extruder_axis_index])
            except Exception:
                try:
                    axis_r = float(mv.axes_r[3])
                except Exception:
                    axis_r = 0.0

            if axis_r <= 0.0:
                continue

            try:
                accel = float(mv.accel) * axis_r
            except Exception:
                accel = 0.0

            try:
                start_v = float(mv.start_v) * axis_r
            except Exception:
                start_v = 0.0

            try:
                cruise_v = float(mv.cruise_v) * axis_r
            except Exception:
                cruise_v = 0.0

            synthesized = {
                'start_time': float(m_start),
                'end_time': float(m_end),
                'accel_t': float(mv.accel_t),
                'cruise_t': float(mv.cruise_t),
                'decel_t': float(mv.decel_t),
                'start_v': float(start_v),
                'cruise_v': float(cruise_v),
                'accel': float(accel),
                'axis_r': float(axis_r),
            }

            if window_start is None:
                window_start = synthesized
                window_end = synthesized
                continue

            if m_start > (window_end['end_time'] + gap_tolerance_s):
                break
            if m_end > window_end['end_time']:
                window_end = synthesized

        if window_start is None:
            return None, None, pending_tail
        return window_start, window_end, pending_tail

    def get_status(self, eventtime):
        est = self._estimated_print_time(eventtime)
        self._prune(est)

        queue_end = self._moves[-1]['end_time'] if self._moves else est
        queue_tail_s = None
        if est is not None and queue_end is not None:
            queue_tail_s = max(0.0, float(queue_end) - float(est))

        active_print = None
        if est is not None:
            candidate = self._find_move_at(est)
            if self._is_print_move(candidate):
                active_print = candidate

        first_print = self._first_print_move_after(est)
        next_window_start, next_window_end = self._print_window_from_move(first_print)
        current_window_start, current_window_end = self._print_window_from_move(active_print)

        if current_window_end is not None:
            next_window_start, next_window_end = self._next_print_window_after(
                current_window_end['end_time']
            )

        pending_start, pending_end, pending_tail = self._pending_lookahead_print_window(est)
        if pending_tail is not None:
            if queue_end is None:
                queue_end = pending_tail
            else:
                queue_end = max(float(queue_end), float(pending_tail))

        if pending_start is not None:
            if (
                next_window_start is None
                or pending_start['start_time'] < next_window_start['start_time']
            ):
                next_window_start, next_window_end = pending_start, pending_end

        if est is not None and queue_end is not None:
            queue_tail_s = max(0.0, float(queue_end) - float(est))

        print_window_active = (current_window_start is not None) or (next_window_start is not None)

        time_to_print_start_s = None
        if est is not None:
            if next_window_start is not None:
                time_to_print_start_s = max(0.0, float(next_window_start['start_time']) - float(est))
            elif current_window_start is not None:
                time_to_print_start_s = 0.0

        time_to_print_stop_s = None
        if est is not None and current_window_end is not None:
            time_to_print_stop_s = max(0.0, float(current_window_end['end_time']) - float(est))

        control_velocity_mms = 0.0
        if est is not None:
            if active_print is not None:
                v = self._velocity_in_move(active_print, est)
                if v is not None:
                    control_velocity_mms = max(0.0, float(v))
            elif (
                next_window_start is not None
                and time_to_print_start_s is not None
            ):
                sample_t = min(
                    next_window_start['end_time'],
                    next_window_start['start_time'] + 0.05,
                )
                v = self._velocity_in_move(next_window_start, sample_t)
                if v is not None:
                    control_velocity_mms = max(0.0, float(v))

        out = {
            'available': self.status['available'],
            'estimated_print_time': est,
            'queue_tail_s': queue_tail_s,
            'print_window_active': bool(print_window_active),
            'time_to_print_start_s': time_to_print_start_s,
            'time_to_print_stop_s': time_to_print_stop_s,
            'control_velocity_mms': control_velocity_mms,
        }

        self.status.update(out)

        if self.debug_enabled:
            first_t = self._moves[0]['start_time'] if self._moves else None
            last_t = self._moves[-1]['end_time'] if self._moves else None
            logging.info(
                "drukmix_planner_probe status: est=%s moves=%d first=%s last=%s tail=%s active=%s next_start=%s current_stop=%s control_velocity=%s",
                est,
                len(self._moves),
                first_t,
                last_t,
                queue_tail_s,
                active_print['start_time'] if active_print is not None else None,
                time_to_print_start_s,
                time_to_print_stop_s,
                control_velocity_mms,
            )

        return dict(self.status)


def load_config(config):
    return DrukMixPlannerProbe(config)

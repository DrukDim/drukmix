import logging
from collections import deque

KEEP_HISTORY_S = 5.0


class DrukMixProbe:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.toolhead = None
        self.mcu = None
        self.extruder_name = config.get('extruder', 'extruder')
        self.extruder_obj = None
        self._orig_process_move = None

        # mirror of flushed/active moves
        self._active_moves = deque()

        self.debug_enabled = config.getboolean('debug_enabled', False)
        self.debug_every_n_moves = config.getint('debug_every_n_moves', 200)
        self._debug_move_counter = 0

        self.print_velocity_epsilon = config.getfloat(
            'print_velocity_epsilon', 0.001, minval=0.0
        )
        self.pump_start_lookahead_s = config.getfloat(
            'pump_start_lookahead_s', 3.0, minval=0.0
        )
        self.pump_stop_lookahead_s = config.getfloat(
            'pump_stop_lookahead_s', 3.0, minval=0.0
        )

        self.status = {
            'available': False,
            'extruder': self.extruder_name,
            'estimated_print_time': None,
            'queue_end_print_time': None,
            'queue_tail_s': None,
            'data_source': 'hybrid_probe',
            'print_window_active': False,
            'time_to_print_start_s': None,
            'time_to_print_stop_s': None,
            'planned_start_velocity_mms': 0.0,
            'planned_start_velocity_is_zero': True,
            'active_control_velocity_mms': 0.0,
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
            "drukmix_probe connected: extruder=%s available=%s hooked=%s",
            self.extruder_name,
            self.status['available'],
            self._orig_process_move is not None,
        )

    def _install_hook(self):
        if self.extruder_obj is None or self._orig_process_move is not None:
            return

        orig = self.extruder_obj.process_move
        probe = self

        def wrapped_process_move(print_time, move, ea_index):
            axis_r = move.axes_r[ea_index]
            accel = move.accel * axis_r
            start_v = move.start_v * axis_r
            cruise_v = move.cruise_v * axis_r
            end_v = move.end_v * axis_r
            total_t = move.accel_t + move.cruise_t + move.decel_t
            end_time = print_time + total_t

            probe._active_moves.append({
                'start_time': float(print_time),
                'end_time': float(end_time),
                'accel_t': float(move.accel_t),
                'cruise_t': float(move.cruise_t),
                'decel_t': float(move.decel_t),
                'start_v': float(start_v),
                'cruise_v': float(cruise_v),
                'end_v': float(end_v),
                'accel': float(accel),
                'axis_r': float(axis_r),
                'start_pos': float(move.start_pos[ea_index]),
                'can_pressure_advance': bool(
                    axis_r > 0.0 and (move.axes_d[0] or move.axes_d[1])
                ),
            })

            probe._debug_move_counter += 1
            if probe.debug_enabled:
                if probe._debug_move_counter <= 5 or (
                    probe._debug_move_counter % max(1, probe.debug_every_n_moves)
                ) == 0:
                    logging.info(
                        "drukmix_probe active_move: n=%d pt=%.6f ea=%s axis_r=%.6f start_v=%.6f cruise_v=%.6f end_v=%.6f accel_t=%.6f cruise_t=%.6f decel_t=%.6f end=%.6f",
                        probe._debug_move_counter,
                        float(print_time),
                        ea_index,
                        float(axis_r),
                        float(start_v),
                        float(cruise_v),
                        float(end_v),
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

    def _prune_active(self, est):
        if est is None:
            return
        cutoff = est - KEEP_HISTORY_S
        while self._active_moves and self._active_moves[0]['end_time'] < cutoff:
            self._active_moves.popleft()

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

    def _find_active_move_at(self, est):
        for m in self._active_moves:
            if m['start_time'] <= est <= m['end_time']:
                return m
        return None

    def _get_future_queue(self):
        if self.toolhead is None:
            return []
        la = getattr(self.toolhead, "lookahead", None)
        if la is None:
            return []
        q = getattr(la, "queue", None)
        if q is None:
            return []
        return list(q)

    def _future_move_to_probe_dict(self, move, start_time):
        axis_r = move.axes_r[3]
        start_v = move.start_v * axis_r
        cruise_v = move.cruise_v * axis_r
        end_v = move.end_v * axis_r
        total_t = move.accel_t + move.cruise_t + move.decel_t

        return {
            'start_time': float(start_time),
            'end_time': float(start_time + total_t),
            'accel_t': float(move.accel_t),
            'cruise_t': float(move.cruise_t),
            'decel_t': float(move.decel_t),
            'start_v': float(start_v),
            'cruise_v': float(cruise_v),
            'end_v': float(end_v),
            'accel': float(move.accel * axis_r),
            'axis_r': float(axis_r),
        }

    def _collect_future_moves(self, est):
        out = []
        if est is None:
            return out
        next_start = float(est)
        for move in self._get_future_queue():
            if len(move.axes_d) < 4:
                continue
            if not move.axes_d[3]:
                next_start += move.accel_t + move.cruise_t + move.decel_t
                continue
            pm = self._future_move_to_probe_dict(move, next_start)
            next_start = pm['end_time']
            if not self._is_print_move(pm):
                continue
            out.append(pm)
        return out

    def get_status(self, eventtime):
        est = self._estimated_print_time(eventtime)
        self._prune_active(est)

        future_moves = self._collect_future_moves(est)
        first_print = future_moves[0] if future_moves else None
        last_print = future_moves[-1] if future_moves else None

        queue_end = last_print['end_time'] if last_print is not None else est
        tail = None
        if est is not None and queue_end is not None:
            tail = max(0.0, float(queue_end) - float(est))

        time_to_print_start_s = None
        if est is not None and first_print is not None:
            time_to_print_start_s = max(0.0, float(first_print['start_time']) - float(est))

        time_to_print_stop_s = None
        if est is not None and last_print is not None:
            time_to_print_stop_s = max(0.0, float(last_print['end_time']) - float(est))

        print_window_active = bool(last_print is not None)

        planned_start_velocity_mms = 0.0
        planned_start_velocity_is_zero = True
        if first_print is not None:
            planned_start_velocity_mms = max(0.0, float(first_print['start_v']))
            planned_start_velocity_is_zero = planned_start_velocity_mms <= self.print_velocity_epsilon

        active_control_velocity_mms = 0.0
        if est is not None:
            active_move = self._find_active_move_at(est)
            if self._is_print_move(active_move):
                v = self._velocity_in_move(active_move, est)
                if v is not None:
                    active_control_velocity_mms = max(0.0, float(v))

        out = {
            'available': self.status['available'],
            'extruder': self.extruder_name,
            'estimated_print_time': est,
            'queue_end_print_time': queue_end,
            'queue_tail_s': tail,
            'data_source': 'hybrid_probe',
            'print_window_active': bool(print_window_active),
            'time_to_print_start_s': time_to_print_start_s,
            'time_to_print_stop_s': time_to_print_stop_s,
            'planned_start_velocity_mms': planned_start_velocity_mms,
            'planned_start_velocity_is_zero': bool(planned_start_velocity_is_zero),
            'active_control_velocity_mms': active_control_velocity_mms,
        }

        self.status.update(out)

        if self.debug_enabled:
            logging.info(
                "drukmix_probe status: est=%s future_moves=%d active_moves=%d tail=%s t_start=%s t_stop=%s planned_start_v=%s start_is_zero=%s active_v=%s",
                est,
                len(future_moves),
                len(self._active_moves),
                tail,
                time_to_print_start_s,
                time_to_print_stop_s,
                planned_start_velocity_mms,
                planned_start_velocity_is_zero,
                active_control_velocity_mms,
            )

        return dict(self.status)


def load_config(config):
    return DrukMixProbe(config)

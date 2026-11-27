"""Observe original clocks and display data; no replacement clock or UI."""
import time
import uuid

from .move_observe import MoveObserver, move_state


def dc_state(session):
    return {**move_state(session), "mode": session.mode, "minutes": session.minutes,
            "white": session.white["name"] if session.white else "",
            "black": session.black["name"] if session.black else "",
            "game_status": session.game.status() if session.game else "",
            "last_move": session.last_move, "last_tick": session.last_tick,
            "rounded_clocks_ms": list(session.clock_values())}


class DisplayClockObserver(MoveObserver):
    def install(self):
        from ui_game import GameSession
        from ui_service import UiCore
        from scb_link import ScbLink
        self.dc_codes = {getattr(GameSession, name).__code__: "GameSession." + name for name in
                         ("prepare", "start", "commit", "on_board", "pause", "resume", "end",
                          "connection", "tick", "tick_clock_only")}
        self.dc_codes[UiCore.handle.__code__] = "UiCore.handle"
        self.dc_codes[UiCore.latch_fault.__code__] = "UiCore.latch_fault"
        self.failure_codes = {ScbLink._read_loop.__code__, ScbLink._heartbeat_loop.__code__, ScbLink.close.__code__}
        self.close_code = ScbLink.close.__code__
        self.dc_pending = {}
        super().install()
        self.codes.update(self.dc_codes)
        self.codes.update({code: "serial_worker" for code in self.failure_codes})
        self.emit("display_clock_observer_ready", version=1)

    def observe(self, frame, event, arg, name):
        now = time.monotonic_ns()
        if frame.f_code in self.failure_codes:
            obj = frame.f_locals["self"]
            phase = "call" if frame.f_code is self.close_code else "return"
            if event == phase and obj._failure is not None:
                self.emit("dc_link_failure", observed_ns=now, error=str(obj._failure),
                          error_type=type(obj._failure).__name__, port=obj.serial.port,
                          intentional_stop=obj._stop.is_set(), source=frame.f_code.co_name)
            return
        if name == "Server.send" and event == "return":
            obj, message = frame.f_locals["self"], frame.f_locals.get("message", {})
            if obj.client is not None and message.get("type") == "state":
                self.emit("dc_state", observed_ns=now, state=dc_state(obj.core.session), payload=message)
        if frame.f_code in self.dc_codes:
            operation = self.dc_codes[frame.f_code]
            local, parent = frame.f_locals, frame.f_back
            obj = local["self"]
            session = obj.session if operation.startswith("UiCore.") else obj
            state = dc_state(session)
            if event == "call":
                token = uuid.uuid4().hex
                self.dc_pending[id(frame)] = (token, now)
                data = {k: local[k] for k in ("request", "move", "verified", "reason", "connected", "result") if k in local}
                if operation == "UiCore.handle":
                    data["production_ui_dispatch"] = bool(parent and parent.f_code is self.ui_caller)
                if operation == "GameSession.connection":
                    data["production_io_dispatch"] = bool(parent and parent.f_code is self.serial_caller)
                self.emit("dc_call", operation=operation, token=token, observed_ns=now, state=state, data=data)
            elif event == "return":
                token, started = self.dc_pending.pop(id(frame), (None, None))
                self.emit("dc_return", operation=operation, token=token, started_ns=started,
                          observed_ns=now, state=state, value=arg)
        # Retain existing sensor, rules, request, database and cleanup observations.
        # New methods absent from MoveObserver still use its base fallback safely.
        if frame.f_code in self.extra or name in {"Server.send", "Server.__init__", "parse_frame",
                                                  "ScbLink._write", "GameStore.move", "GameStore.checkpoint",
                                                  "GameStore.history", "GameStore.review"}:
            super().observe(frame, event, arg, name)

"""Observe the existing feedback path; never drive LEDs from a profiling callback."""
import time
import uuid
from types import CodeType

from .display_clock_observe import DisplayClockObserver, dc_state


class LedObserver(DisplayClockObserver):
    def install(self):
        from ui_service import UiCore
        self.feedback_code = UiCore.feedback_update.__code__
        self.feedback_senders = {code for code in self.feedback_code.co_consts if isinstance(code, CodeType)}
        self.last_desired = {}
        super().install()
        self.codes[self.feedback_code] = "UiCore.feedback_update"
        self.emit("led_observer_ready", version=1)

    def observe(self, frame, event, arg, name):
        now = time.monotonic_ns()
        if frame.f_code is self.feedback_code:
            core = frame.f_locals["self"]
            desired = core.session.feedback_command  # Production string attribute, not a callable.
            if event == "call" and self.last_desired.get(id(core)) != desired:
                self.last_desired[id(core)] = desired
                self.emit("led_input", token=uuid.uuid4().hex, observed_ns=now, desired=desired,
                          previous_sent=core.led_sent, busy=core.led_job is not None,
                          connected=core.link is not None, fault=core.fault, state=dc_state(core.session))
            return
        if name == "GameStore.move" and event == "return":
            # Python return occurs after the original SQLite transaction exits but
            # BEFORE GameSession swaps the accepted game or generates feedback.
            parent = frame.f_back
            state = dc_state(parent.f_locals["self"]) if parent and parent.f_code in self.dc_codes and \
                self.dc_codes[parent.f_code] == "GameSession.commit" else None
            self.emit("led_store_return", observed_ns=now, game_id=frame.f_locals["game_id"],
                      ply=frame.f_locals["ply"], uci=frame.f_locals["uci"], accepted_before_swap=state)
            # An exceptional Python return also has value None. Only a subsequent
            # successful commit with a verified DB snapshot may use this anchor.
        if name == "ScbLink._write" and event == "call":
            command = frame.f_locals.get("command", "")
            if command.split() and command.split()[0] in {"GUIDE", "MARK", "LED", "LED_CLEAR"}:
                caller = frame.f_back.f_back if frame.f_back else None
                self.emit("led_command", observed_ns=now, command=command,
                          request_id=frame.f_locals["request_id"],
                          production_feedback_path=bool(caller and caller.f_code in self.feedback_senders))
        if name == "parse_frame" and event == "return" and arg is not None:
            if arg.kind in {"ACK", "PLATFORM"}:
                self.emit("led_transport", observed_ns=now, frame_kind=arg.kind,
                          request_id=arg.request_id, payload=arg.payload, received_at=arg.received_at,
                          optical_measurement=False)
        super().observe(frame, event, arg, name)

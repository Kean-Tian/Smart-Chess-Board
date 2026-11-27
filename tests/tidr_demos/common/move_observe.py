"""Additional observations of original validation calls; no sensor or decision injection."""
import time
import uuid

from .observe import Observer, session_state
from .runtime import database_snapshot


def move_state(session):
    return {**session_state(session), "ambiguous": session.ambiguous,
            "guidance": session.guidance, "legal_source": session.legal_source,
            "legal_destinations": list(session.legal_destinations),
            "pending": session.pending, "board_generation": session.board_generation,
            "feedback_command": session.feedback_command}


class MoveObserver(Observer):
    VERSION = 1

    def install(self):
        from ui_game import GameSession
        from ui_service import UiCore, Server
        from scb_rules import Game
        from board_game import expected_occupancy
        self.extra = {f.__code__: name for name, f in {
            "GameSession.event": GameSession.event,
            "GameSession.commit": GameSession.commit,
            "GameSession.on_board": GameSession.on_board,
            "GameSession.set_guidance": GameSession.set_guidance,
            "UiCore.handle": UiCore.handle,
            "Game.legal_moves": Game.legal_moves,
            "expected_occupancy": expected_occupancy,
        }.items()}
        self.serial_caller = UiCore.update.__code__
        self.ui_caller = Server.run.__code__
        self.extra_pending = {}
        super().install()
        self.codes.update(self.extra)
        self.emit("move_observer_ready", version=self.VERSION)

    def observe(self, frame, event, arg, name):
        if frame.f_code not in self.extra:
            if name == "Server.send" and event == "return" and frame.f_locals["self"].client is not None:
                message = frame.f_locals.get("message", {})
                if message.get("type") == "state":
                    self.emit("mv_state", version=self.VERSION,
                              state=move_state(frame.f_locals["self"].core.session))
            return super().observe(frame, event, arg, name)
        now = time.monotonic_ns()  # Endpoint sampled BEFORE snapshots or evidence serialization.
        local, parent = frame.f_locals, frame.f_back
        obj = local.get("self")
        if name in {"Game.legal_moves", "expected_occupancy"}:
            caller = self.extra.get(parent.f_code) if parent else None
            if caller in {"GameSession.event", "GameSession.commit"}:
                self.emit("mv_query", operation=name, phase=event, observed_ns=now, caller=caller,
                          parent_token=self.extra_pending.get(id(parent), (None,))[0],
                          value=arg if event == "return" else None)
            return
        if event == "call":
            token = uuid.uuid4().hex
            self.extra_pending[id(frame)] = (token, now)
            session = obj.session if name == "UiCore.handle" else obj
            data = {"state": move_state(session)}
            for key in ("payload", "mask", "move", "explicit", "enabled", "request"):
                if key in local:
                    data[key] = local[key]
            if name == "GameSession.event":
                sensor = parent.f_locals.get("frame") if parent else None
                actual = (parent is not None and parent.f_code is self.serial_caller and
                          sensor is not None and sensor.kind == "EVENT" and sensor.payload == local["payload"])
                data["production_serial_dispatch"] = bool(actual)
                data["received_ns"] = round(sensor.received_at * 1e9) if actual else None
            if name == "UiCore.handle":
                data["production_ui_dispatch"] = bool(parent and parent.f_code is self.ui_caller)
            if name == "GameSession.commit":
                data["snapshot"] = database_snapshot(self.manifest["database"])
            self.emit("mv_call", operation=name, token=token, observed_ns=now, data=data)
        else:
            token, started = self.extra_pending.pop(id(frame), (None, None))
            session = obj.session if name == "UiCore.handle" else obj
            data = {"state": move_state(session), "return": arg}
            if name == "GameSession.commit":
                data["snapshot"] = database_snapshot(self.manifest["database"])
            self.emit("mv_return", operation=name, token=token, observed_ns=now,
                      started_ns=started, data=data)

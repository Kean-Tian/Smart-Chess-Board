"""Observe original code objects with profiling; never replace production functions."""
import json
import os
import sys
import threading
import time
import uuid

from .runtime import boot_id, database_snapshot, no_symlinks, stamp


def session_state(session):
    if session is None:
        return None
    return {"game_id": session.game_id, "fen": session.game.fen() if session.game else "",
            "moves": list(session.game.move_history) if session.game else [],
            "active": session.active, "paused": session.paused, "restore": session.restore,
            "clocks": list(session.clocks), "result": session.result,
            "mask": session.mask, "connected": session.connected,
            "message": session.message}


class Observer:
    def __init__(self, run, manifest):
        self.run, self.manifest = run, manifest
        self.session_id = uuid.uuid4().hex
        self.boot = boot_id()
        self.file = no_symlinks(run / "events.jsonl").open("a", buffering=1)
        self.lock = threading.RLock()
        self.pending = {}
        self.codes = {}
        self.errors = 0
        self.installed = False

    def emit(self, kind, **data):
        with self.lock:
            self.file.write(json.dumps({**stamp(), "session": self.session_id,
                                       "boot_id": self.boot, "kind": kind, **data},
                                      separators=(",", ":")) + "\n")

    def install(self):
        import ui_service
        from game_store import GameStore
        from ui_game import GameSession
        from scb_link import ScbLink, parse_frame
        functions = {
            "Server.__init__": ui_service.Server.__init__,
            "Server.send": ui_service.Server.send,
            "UiCore.handle": ui_service.UiCore.handle,
            "GameSession.commit": GameSession.commit,
            "GameSession.end": GameSession.end,
            "GameSession.on_board": GameSession.on_board,
            "GameStore.move": GameStore.move,
            "GameStore.checkpoint": GameStore.checkpoint,
            "GameStore.history": GameStore.history,
            "GameStore.review": GameStore.review,
            "ScbLink._write": ScbLink._write,
            "parse_frame": parse_frame,
        }
        self.codes = {f.__code__: name for name, f in functions.items()}
        if sys.getprofile() is not None or threading.getprofile() is not None:
            raise RuntimeError("Existing profiler present; refusing to replace it")
        self.emit("observer_start", pid=os.getpid(), database=self.manifest["database"],
                  purpose=self.manifest["purpose"], instrumentation="Python call/return profiling")
        threading.setprofile(self.profile)
        sys.setprofile(self.profile)
        self.installed = True

    def profile(self, frame, event, arg):
        name = self.codes.get(frame.f_code)
        if name is None or event not in {"call", "return"}:
            return
        try:
            self.observe(frame, event, arg, name)
        except Exception as exc:
            self.errors += 1
            # Observation failure never changes a production return value or suppresses a fault.
            try:
                self.emit("observer_error", operation=name, error=str(exc))
            except Exception:
                pass

    def observe(self, frame, event, arg, name):
        local = frame.f_locals
        obj = local.get("self")
        if name == "ScbLink._write":
            if event == "call":
                self.emit("serial_request", command=local.get("command"),
                          request_id=local.get("request_id"))
            return
        if name == "parse_frame":
            if event == "return" and arg is not None:
                if arg.kind in {"BOARD", "EVENT", "SNAPSHOT", "STATUS", "HELLO", "FAULT", "ERR"}:
                    self.emit("serial_reply", frame_kind=arg.kind, payload=arg.payload,
                              received_at=arg.received_at)
            return
        if name == "Server.send":
            # Record replies only after production queued them for its actual UI client.
            if event == "return" and obj.client is not None and isinstance(local.get("message"), dict):
                message = local["message"]
                if message.get("type") == "state":
                    self.emit("state", state=session_state(obj.core.session))
                elif message.get("type") in {"review", "history"}:
                    self.emit("ui_reply", message=message)
            return
        if name == "Server.__init__":
            if event == "return" and hasattr(obj, "core"):
                self.emit("service_ready", snapshot=database_snapshot(self.manifest["database"]))
            return
        if name == "GameSession.on_board":
            if event == "call":
                self.emit("board_delivery", mask=local.get("mask"))
            return
        if event == "call":
            token = uuid.uuid4().hex
            self.pending[id(frame)] = (token, time.monotonic_ns())
            data = {k: local[k] for k in ("request", "game_id", "ply", "move", "uci", "fen",
                                         "result", "status", "explicit") if k in local}
            if name.startswith("GameSession."):
                data["state"] = session_state(obj)
            if name == "UiCore.handle":
                data["state"] = session_state(obj.session)
            if name in {"GameStore.move", "GameStore.checkpoint"}:
                data["storage"] = {"synchronous": obj.db.execute("PRAGMA synchronous").fetchone()[0],
                                   "journal_mode": obj.db.execute("PRAGMA journal_mode").fetchone()[0]}
            self.emit("call", operation=name, token=token, data=data)
        else:
            token, started = self.pending.pop(id(frame), (None, None))
            data = {"return": arg if isinstance(arg, (dict, list, str, int, float, bool, type(None))) else None}
            if name.startswith("GameSession."):
                data["state"] = session_state(obj)
                # Separate read-only connection proves committed visibility, not a writer's cache.
                data["snapshot"] = database_snapshot(self.manifest["database"])
                data["availability_ns"] = time.monotonic_ns()
            if name == "UiCore.handle":
                data["state"] = session_state(obj.session)
            self.emit("return", operation=name, token=token, started_ns=started, data=data)

    def close(self):
        if self.installed:
            sys.setprofile(None)
            threading.setprofile(None)
        self.emit("observer_stop", errors=self.errors)
        self.file.flush()
        os.fsync(self.file.fileno())
        self.file.close()

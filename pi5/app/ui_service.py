"""Local Unix-socket service connecting native UI, SQLite, chess rules and MCU.

Manual execution is the default. Automatic execution requires explicit runtime
opt-in and a user request. All rules/database mutations stay on the state loop.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import queue
import re
import selectors
import signal
import socket
import time
import threading

from game_store import GameStore
from scb_link import ScbLink, DeviceError
from ui_game import GameSession
from ui_hardware import execute_motion, reset_fault, stopped_status, fresh_snapshot
from led_diagnostics import LedDiagnostics


def socket_path():
    # 本机进程间通道的文件路径，不是网络地址或 USB 设备路径。
    if os.environ.get("SCB_UI_SOCKET"):
        return Path(os.environ["SCB_UI_SOCKET"])
    base = Path(os.environ.get("XDG_RUNTIME_DIR") or Path.home() / ".local" / "share" / "scb")
    return base / "scb-ui.sock"


def ports():
    try:
        from serial.tools import list_ports
        return [{"port": p.device, "description": p.description or p.device}
                for p in list_ports.comports() if p.vid is not None][:8]
    except ImportError:
        return []


def fields(frame):
    return dict(token.split("=", 1) for token in frame.payload.split() if "=" in token)



class UiCore:
    def __init__(self, store, *, link_factory=None, session=None, now=time.monotonic, automatic_motion=None):
        self.store, self.now = store, now
        self.session = session or GameSession(store, now=now)
        self.link_factory = link_factory or (lambda port: ScbLink.open(port, exclusive=True))
        self.link = None
        self.io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scb-usb")
        self.job = None
        self.job_kind = None
        self.motion_io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scb-motion")
        self.led_io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scb-led")
        self.led_diagnostics = LedDiagnostics(self.led_io, now)
        self.stop_io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scb-stop")
        self.stop_job = None
        self.motion_job = self.led_job = None
        self.motion_cancel = threading.Event()
        self.motion_context = None
        self.led_sent = None
        self.led_context = None
        self.automatic_motion = (os.environ.get("SCB_AUTOMATIC_MOTION") == "1"
                                 if automatic_motion is None else automatic_motion)
        settings = store.board_settings()
        self.port = settings["port"]
        self.available_ports = []
        self.last_ports = -10.0
        self.last_poll = -10.0
        self.fault, self.notice = "", ""
        self.check_after = None
        self.board_status = {}
        self.scan_timing = {}
        self.scan_round_trip_ms = None
        self.sensor_rows = {}
        self.diagnostic_error = ""
        self.board_barrier = 0.0

    def stop_motion(self):
        # STOP uses the short-request worker, so a long MOVE wait cannot delay it.
        if self.motion_job or self.session.motion_active:
            self.motion_cancel.set()
            self.session.cancel_motion()
            if self.link and (not self.stop_job or self.stop_job.done()):
                link = self.link
                self.stop_job = self.stop_io.submit(lambda: link.request("STOP", timeout=0.6))

    def latch_fault(self, reason):
        self.fault = str(reason)
        self.led_diagnostics.stop(exit_mode=True)
        self.check_after = None
        self.session.ready = False
        self.stop_motion()
        if self.session.active:
            self.session.pause(f"Board fault: {reason}. Resolve it, reset fault, then Resume.")

    def feedback_update(self):
        if self.led_job and self.led_job.done():
            job, context = self.led_job, self.led_context
            self.led_job = self.led_context = None
            try:
                job.result()
                if context[0] is self.link:
                    self.led_sent = context[1]
            except Exception as exc:
                if context[0] is self.link:
                    self.latch_fault(f"LED feedback failed: {exc}")
        if self.led_diagnostics.owned:
            return  # Drain previous normal feedback, but never compete with diagnostic ownership.
        desired = self.session.feedback_command
        if self.link and not self.led_job and desired != self.led_sent and not self.fault:
            link = self.link
            self.led_context = (link, desired)
            self.led_job = self.led_io.submit(lambda: link.request(desired, timeout=0.4))

    def submit(self, kind, operation):
        # USB 请求可能等待回复，交给单独线程，主循环继续处理状态。
        if self.job:
            raise ValueError("USB operation in progress. Please wait.")
        self.job_kind = kind
        self.job = self.io.submit(operation)

    def handle(self, request):
        # 接收 UI 的 JSON 命令，分发给棋盘连接或游戏状态模块。
        cmd = request.get("cmd")
        if isinstance(cmd, str) and cmd.startswith("led_diag_"):
            return self.handle_led_diagnostic(request)
        if self.led_diagnostics.owned and cmd in {"prepare", "start", "resume", "execute_computer", "commit", "confirm_computer"}:
            raise ValueError("Exit LED diagnostics and wait for an acknowledged clear before gameplay")
        self.session.tick_clock_only()
        self.notice = ""
        if cmd == "connect":
            if self.link or (self.job and self.job_kind == "connect"):
                return None
            port = request.get("port", "") or os.environ.get("SCB_SERIAL_PORT", "")
            if not port and len(self.available_ports) == 1:
                port = self.available_ports[0]["port"]
            if not isinstance(port, str) or not port.startswith("/dev/") or len(port) > 128 or any(ord(c) < 32 for c in port):
                raise ValueError("Choose a USB serial port in board setup")
            self.port = port
            self.store.save_board_port(port)
            self.session.message = "Connecting to board..."
            self.submit("connect", lambda: self.link_factory(port))
        elif cmd == "disconnect":
            if not self.link or (self.job and self.job_kind == "disconnect"):
                return None
            if self.job:
                raise ValueError("USB operation in progress. Please wait.")
            self.latch_fault("USB disconnected")
            old, self.link = self.link, None
            self.session.connection(False)
            self.check_after = None
            self.board_status, self.scan_timing, self.sensor_rows = {}, {}, {}
            self.scan_round_trip_ms = None
            if old:
                self.submit("disconnect", old.close)
        elif cmd == "prepare":
            if self.motion_job:
                raise ValueError("Wait for motion to stop before preparing another game")
            self.session.prepare(request.get("mode"), request.get("white_id"), request.get("black_id"),
                                 request.get("human", "w"), request.get("minutes"), request.get("guidance"),
                                 request.get("coach_white"), request.get("coach_black"))
        elif cmd == "scan":
            if not self.link:
                raise ValueError("Connect the board before scanning")
            self.diagnostic_error = ""
            self.submit("poll", lambda: self.poll_board(diagnostics=True))
        elif cmd == "guidance":
            self.session.set_guidance(request.get("enabled"))
        elif cmd == "coaching":
            self.session.set_coaching(request.get("side"), request.get("enabled"))
        elif cmd == "check":
            if not self.link:
                raise ValueError("Connect the board in game setup first")
            if self.job:
                raise ValueError("USB operation in progress. Please try again shortly.")
            if self.session.game is None or self.session.active:
                raise ValueError("Prepare a new game first")
            self.session.ready = self.session.verified = False
            self.check_after = self.session.board_generation
            self.session.message = "Checking a fresh full-board occupancy frame..."
            self.submit("poll", self.poll_board)
        elif cmd == "start":
            if self.session.active:
                return None
            if self.fault:
                raise ValueError("Resolve the board fault and use Reset fault before starting")
            self.session.start(request.get("verified"))
        elif cmd == "pause":
            if self.session.motion_active:
                self.latch_fault("Motion interrupted by Pause")
            self.session.pause()
        elif cmd == "resume":
            if self.session.active and not self.session.paused:
                return None
            if self.fault:
                raise ValueError("Resolve the board fault and use Reset fault before resuming")
            if not self.link or self.motion_job:
                raise ValueError("Reconnect and wait for motion to stop before resuming")
            if self.job and self.job_kind == "resume":
                return None
            link = self.link
            def verify_resume():
                stopped_status(link)
                mask = fresh_snapshot(link)
                stopped_status(link)
                return mask
            self.submit("resume", verify_resume)
        elif cmd == "reset_fault":
            if not self.link or self.motion_job:
                raise ValueError("Reconnect and wait for motion to stop before resetting faults")
            link = self.link
            self.submit("reset_fault", lambda: reset_fault(link))
        elif cmd == "execute_computer":
            if not self.automatic_motion:
                raise ValueError("Automatic motion is not enabled; execute the move manually")
            if self.fault or not self.link or self.motion_job or self.job:
                raise ValueError("Resolve faults and wait for board operations to finish")
            move = request.get("move")
            self.session.begin_motion(move)
            self.motion_cancel = threading.Event()
            self.motion_context = (self.link, self.session.generation, move)
            self.motion_job = self.motion_io.submit(execute_motion, self.link, move, self.motion_cancel)
        elif cmd == "end":
            if not self.session.active and self.session.game_id:
                return None
            if self.session.motion_active:
                self.latch_fault("Motion interrupted by End game")
            self.session.end(request.get("result", "*"))
        elif cmd == "hint":
            if not self.session.active or self.session.paused or not self.session.synchronized():
                raise ValueError("Resume and synchronize the current board before requesting a hint")
            if self.session.mode == "pvc":
                raise ValueError("Hints and guidance are not available in Vs computer mode")
            if self.session.mode == "coach":
                if not self.session.coaching[self.session.game.fen().split()[1]]:
                    raise ValueError("The current player has AI coaching OFF")
            else:
                self.session.set_guidance(True)
            self.session.maybe_search(force_hint=True)
        elif cmd == "confirm_computer":
            move = request.get("move")
            if not self.session.computer_move or move != self.session.computer_move:
                raise ValueError("The requested computer move has changed")
            self.session.commit(move, explicit=True)
        elif cmd == "commit":
            move = request.get("move", "")
            if not isinstance(move, str) or not re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", move):
                raise ValueError("Enter a UCI move such as e2e4 or e7e8q")
            self.session.commit(move, explicit=True)
        elif cmd == "history":
            return self.store.history(request.get("offset", 0))
        elif cmd == "review":
            return self.store.review(request.get("game_id"), request.get("ply", 0))
        elif cmd not in {"state", "ports"}:
            raise ValueError("Unknown UI command")
        return None

    def handle_led_diagnostic(self, request):
        """Diagnostic namespace: no GameSession mutator, clock tick or store write."""
        cmd = request.get("cmd")
        diagnostic = self.led_diagnostics
        if cmd in {"led_diag_exit", "led_diag_stop", "led_diag_clear"}:
            diagnostic.stop(exit_mode=cmd == "led_diag_exit")
            return None
        if (self.session.active or self.session.paused or self.motion_job or self.session.motion_active
                or self.stop_job or self.fault):
            raise ValueError("LED diagnostics unavailable: end the game and resolve board faults first")
        if not self.link:
            raise ValueError("Connect the board in Sensor Test first")
        if cmd == "led_diag_enter":
            diagnostic.enter(request.get("mode"), self.link)
        elif cmd in {"led_diag_start", "led_diag_restart"}:
            if not diagnostic.owned:
                diagnostic.enter("auto", self.link)
            diagnostic.start()
        elif cmd == "led_diag_pause":
            diagnostic.pause()
        elif cmd == "led_diag_resume":
            diagnostic.resume()
        elif cmd == "led_diag_manual":
            diagnostic.manual(request.get("square"), request.get("color"))
        elif cmd == "led_diag_pattern":
            diagnostic.load(request.get("pattern"))
        else:
            raise ValueError("Unknown LED diagnostic command")
        return None

    def poll_board(self, diagnostics=False):
        # 只请求对局需要的整盘数据和状态；MCU 持续独立扫描。
        result = {"owned_motion": self.session.motion_active}
        started = time.monotonic()
        try:
            self.link.request("SCAN", timeout=0.6)
        except DeviceError as exc:
            if str(exc) != "NOT_READY":
                raise
        result["round_trip_ms"] = round((time.monotonic() - started) * 1000, 3)
        result["status"] = fields(self.link.request("STATUS", timeout=0.6))
        if diagnostics:
            # MCU 扫描周期和 USB 往返时间是两个独立测量，不把它们混为一谈。
            try:
                raw = fields(self.link.request("TIMING", timeout=0.6))
                result["timing"] = {k: int(raw[k]) for k in
                                    ("frames", "frame_us", "max_us", "misses", "debounce_us")}
                if any(v < 0 for v in result["timing"].values()):
                    raise ValueError("Invalid timing counters")
            except (DeviceError, ValueError, KeyError) as exc:
                result["diagnostic_error"] = f"Scan timing unavailable: {exc}"
        return result

    def update(self):
        # 收取 USB 任务结果和 MCU 事件，再推进游戏时钟与提示。
        now = self.now()
        if now - self.last_ports > 2:
            self.available_ports = ports()
            configured = os.environ.get("SCB_SERIAL_PORT", "")
            if configured.startswith("/dev/") and Path(configured).exists() and not any(p["port"] == configured for p in self.available_ports):
                self.available_ports.insert(0, {"port": configured, "description": "Configured board port"})
            self.last_ports = now
        if self.job and self.job.done():
            future, kind = self.job, self.job_kind
            self.job = self.job_kind = None
            try:
                result = future.result()
                if kind == "connect":
                    self.link = result
                    self.session.connection(True)
                    self.session.message = "Board connected. Waiting for a full scan."
                    self.last_poll = -10.0
                    self.sensor_rows, self.scan_timing, self.board_status = {}, {}, {}
                    self.scan_round_trip_ms = None
                    self.diagnostic_error = ""
                    self.led_sent = None
                    if self.fault:
                        self.session.message = "Reconnected. Fault remains latched; resolve it and use Reset fault."
                elif kind == "poll":
                    self.board_status = result["status"]
                    self.scan_round_trip_ms = result["round_trip_ms"]
                    if "timing" in result or "diagnostic_error" in result:
                        self.scan_timing = result.get("timing", {})
                        self.diagnostic_error = result.get("diagnostic_error", "")
                    fault = result["status"].get("fault", "NONE")
                    if fault != "NONE":
                        self.latch_fault(fault)
                    if not result.get("owned_motion") and not self.session.motion_active and any(result["status"].get(key) == "1" for key in ("armed", "moving", "magnet")):
                        self.latch_fault("Unexpected active actuators")
                        self.submit("stop", lambda: self.link.request("STOP", timeout=0.6))
                elif kind in {"reset_fault", "resume"}:
                    mask, self.board_barrier = result
                    self.session.on_board(mask)
                    if self.session.game and not self.session.synchronized():
                        raise ValueError("Restore the accepted board position before reset or resume")
                    if kind == "reset_fault":
                        self.fault = ""
                        self.led_sent = None
                        self.session.message = "Fault reset verified; outputs are off. Press Resume to continue."
                    else:
                        self.session.resume()
            except Exception as exc:
                self.notice = f"Board communication failed: {exc}"
                self.latch_fault(str(exc))
                self.check_after = None
                if self.link and kind not in {"reset_fault", "resume"}:
                    old, self.link = self.link, None
                    try:
                        old.close()
                    except Exception:
                        pass
                if not self.link:
                    self.session.connection(False)
        if self.stop_job and self.stop_job.done():
            job, self.stop_job = self.stop_job, None
            try:
                job.result()
            except Exception as exc:
                self.notice = f"STOP not acknowledged: {exc}. Check actuator power and reconnect."
        if self.link:
            if self.link._failure:
                self.latch_fault("USB disconnected")
                self.notice = "Board disconnected. Reconnect in game setup."
                old, self.link = self.link, None
                old.close()
                self.session.connection(False)
            else:
                for _ in range(256):
                    try:
                        frame = self.link.events.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        if frame.kind in {"BOARD", "EVENT", "SENSOR"} and frame.received_at <= self.board_barrier:
                            continue  # 已由更新的、请求关联的扫描覆盖，不能倒退到旧棋盘。
                        if frame.kind == "BOARD":
                            if not re.fullmatch(r"[0-9a-fA-F]{16}", frame.payload):
                                self.session.board_at = None
                                self.latch_fault("Invalid board data")
                                raise ValueError("Invalid board data")
                            raw = int(frame.payload, 16)
                            self.session.on_board(raw)
                            if self.check_after is not None and self.session.board_generation > self.check_after:
                                self.session.check()
                                self.check_after = None
                        elif frame.kind == "EVENT":
                            self.session.event(frame.payload)
                        elif frame.kind == "SENSOR":
                            row = fields(frame)
                            if re.fullmatch(r"[01]{3}", row.get("mux", "")) and re.fullmatch(r"[01]{8}", row.get("inputs", "")):
                                self.sensor_rows[row["mux"]] = row
                        elif frame.kind == "HELLO":
                            self.session.ready = False
                            if self.session.active:
                                self.latch_fault("Board restarted")
                        elif frame.kind == "FAULT":
                            self.latch_fault(frame.payload)
                    except Exception as exc:
                        self.notice = str(exc)
                if not self.job and now - self.last_poll >= 1.0:
                    self.last_poll = now
                    self.submit("poll", self.poll_board)
        if self.motion_job and self.motion_job.done():
            job, context = self.motion_job, self.motion_context
            self.motion_job = self.motion_context = None
            try:
                mask, barrier = job.result()
                if (context[0] is not self.link or context[1] != self.session.generation or
                        self.motion_cancel.is_set() or self.fault):
                    raise ValueError("Interrupted motion cannot advance the game")
                self.board_barrier = barrier
                self.session.finish_motion(context[2], mask)
            except Exception as exc:
                self.session.cancel_motion()
                self.latch_fault(str(exc))
        self.session.tick()
        if self.session.motion_active and (self.session.paused or not self.session.active):
            self.latch_fault("Motion interrupted by game pause or expiry")
        if self.session.active and not self.session.paused:
            self.session.maybe_search()
        self.feedback_update()
        self.led_diagnostics.update(self.link, normal_busy=self.led_job is not None)

    def state(self):
        # 诊断页面复用同一串口，不另开连接，也不会驱动电机或修改局面。
        state = self.session.state()
        age = None if self.session.board_at is None else max(0, round((self.now() - self.session.board_at) * 1000))
        state.update({"type": "state", "board_connected": self.link is not None,
                      "board_known": self.session.fresh(),
                      "board": f"{self.session.mask:016X}" if self.session.mask is not None and self.session.fresh() else None,
                      "board_age_ms": age, "port": self.port, "ports": self.available_ports,
                      "usb_busy": self.job is not None, "check_pending": self.check_after is not None,
                      "fault": self.fault, "error": self.notice,
                      "automatic_motion_enabled": self.automatic_motion,
                      "motion_busy": self.motion_job is not None,
                      "led_feedback_pending": self.led_job is not None,
                      "engine_error": self.session.hint_error})
        state["led_diagnostics"] = self.led_diagnostics.state()
        expected = None
        if self.session.game:
            from board_game import occupancy, fen_board
            expected = occupancy(fen_board(self.session.game.fen()))
        state.update({"expected_board": f"{expected:016X}" if expected is not None else None,
                      "board_status": self.board_status, "scan_timing": self.scan_timing,
                      "scan_round_trip_ms": self.scan_round_trip_ms,
                      "sensor_rows": self.sensor_rows if self.session.fresh() else {},
                      "diagnostic_error": self.diagnostic_error})
        return state

    def controller_lost(self):
        self.led_diagnostics.stop(exit_mode=True)
        if self.session.motion_active:
            self.latch_fault("UI disconnected during motion")
        if self.session.active and not self.session.paused:
            self.session.tick_clock_only()
            self.session.pause("UI disconnected. Reconnect and resume when ready.")

    def close(self):
        self.stop_motion()
        diagnostic_owned = self.led_diagnostics.owned
        if diagnostic_owned and self.led_job is not None:
            try:
                self.led_job.result()  # Drain older normal feedback before the final diagnostic clear.
            except Exception:
                pass
        self.led_diagnostics.close(self.link)
        if diagnostic_owned:
            print("LED diagnostics: " + self.led_diagnostics.message, flush=True)
        self.motion_io.shutdown(wait=True, cancel_futures=True)
        self.stop_io.shutdown(wait=True, cancel_futures=True)
        self.led_io.shutdown(wait=True, cancel_futures=True)
        self.io.shutdown(wait=True, cancel_futures=True)
        if self.job and self.job_kind == "connect":
            try:
                self.job.result().close()
            except Exception:
                pass
        if self.link:
            self.link.close()
        self.session.close()


class Server:
    # 一个本机控制端连接一个服务，统一管理串口和对局。
    def __init__(self, path, database=None):
        self.path = Path(path)
        if len(os.fsencode(path)) >= 100:
            raise ValueError("Unix socket path is too long")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = open(str(path) + ".lock", "a")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.path.unlink(missing_ok=True)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(path))
        os.chmod(path, 0o600)
        self.listener.listen(1)
        self.listener.setblocking(False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.listener, selectors.EVENT_READ)
        self.client = None
        self.incoming = bytearray()
        self.outgoing = bytearray()
        self.store = GameStore(database)
        self.store.interrupt_previous()
        self.core = UiCore(self.store)
        self.running = True
        self.last_state = -10.0

    def send(self, message):
        if not self.client:
            return
        self.outgoing.extend((json.dumps(message, ensure_ascii=True, separators=(",", ":")) + "\n").encode())
        if len(self.outgoing) > 131072:
            self.drop()

    def drop(self):
        if self.client:
            self.selector.unregister(self.client)
            self.client.close()
            self.client = None
            self.core.controller_lost()
        self.incoming.clear()
        self.outgoing.clear()

    def run(self):
        # 按换行拆分 JSON 请求，更新后台，并持续发送状态。
        while self.running:
            for key, _ in self.selector.select(0.005):
                if key.fileobj is self.listener:
                    client, _ = self.listener.accept()
                    client.setblocking(False)
                    if self.client:
                        client.close()
                    else:
                        self.client = client
                        self.selector.register(client, selectors.EVENT_READ)
                        self.send(self.core.state())
                else:
                    try:
                        chunk = self.client.recv(4096)
                        if not chunk:
                            self.drop()
                            continue
                        self.incoming.extend(chunk)
                        if len(self.incoming) > 16384:
                            self.drop()
                            continue
                        while b"\n" in self.incoming:
                            line, _, tail = self.incoming.partition(b"\n")
                            self.incoming[:] = tail
                            try:
                                request = json.loads(line)
                                if not isinstance(request, dict):
                                    raise ValueError("Expected a command object")
                                reply = self.core.handle(request)
                                if reply:
                                    self.send(reply)
                            except (ValueError, TypeError, OSError, RuntimeError) as exc:
                                self.core.notice = str(exc)
                            except Exception as exc:
                                self.core.notice = f"Operation failed: {type(exc).__name__}: {exc}"
                            self.send(self.core.state())
                    except (ConnectionError, OSError):
                        self.drop()
            board_generation = self.core.session.board_generation
            try:
                self.core.update()
            except Exception as exc:
                self.core.notice = f"Service error: {type(exc).__name__}: {exc}"
            # Push sensor changes immediately; clocks/status target a 20 Hz refresh.
            if self.core.session.board_generation != board_generation or self.now() - self.last_state >= 0.05:
                self.send(self.core.state())
                self.last_state = self.now()
            if self.client and self.outgoing:
                try:
                    sent = self.client.send(self.outgoing)
                    del self.outgoing[:sent]
                except BlockingIOError:
                    pass
                except (ConnectionError, OSError):
                    self.drop()

    @staticmethod
    def now():
        return time.monotonic()

    def close(self):
        self.drop()
        self.core.close()
        self.store.close()
        self.selector.close()
        self.listener.close()
        self.path.unlink(missing_ok=True)
        self.lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, default=socket_path())
    parser.add_argument("--database")
    args = parser.parse_args()
    server = Server(args.socket, args.database)
    def stop(*_):
        server.running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.run()
    finally:
        server.close()


if __name__ == "__main__":
    main()

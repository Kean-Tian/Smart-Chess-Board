"""Local Unix-socket service connecting native UI, SQLite, chess rules and MCU.

The service never arms or commands motors/magnets. Engine searches and serial
requests run outside the state loop; all rules/database mutations stay here.
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

from game_store import GameStore
from scb_link import ScbLink, DeviceError
from ui_game import GameSession


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
    def __init__(self, store, *, link_factory=None, session=None, now=time.monotonic):
        self.store, self.now = store, now
        self.session = session or GameSession(store, now=now)
        self.link_factory = link_factory or (lambda port: ScbLink.open(port, exclusive=True))
        self.link = None
        self.io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scb-usb")
        self.job = None
        self.job_kind = None
        settings = store.board_settings()
        self.port = settings["port"]
        self.available_ports = []
        self.last_ports = -10.0
        self.last_poll = -10.0
        self.fault, self.notice = "", ""
        self.check_after = None

    def submit(self, kind, operation):
        # USB 请求可能等待回复，交给单独线程，主循环继续处理状态。
        if self.job:
            raise ValueError("USB operation in progress. Please wait.")
        self.job_kind = kind
        self.job = self.io.submit(operation)

    def handle(self, request):
        # 接收 UI 的 JSON 命令，分发给棋盘连接或游戏状态模块。
        cmd = request.get("cmd")
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
            self.fault = ""
            self.session.message = "Connecting to board..."
            self.submit("connect", lambda: self.link_factory(port))
        elif cmd == "disconnect":
            if not self.link or (self.job and self.job_kind == "disconnect"):
                return None
            if self.job:
                raise ValueError("USB operation in progress. Please wait.")
            old, self.link = self.link, None
            self.session.connection(False)
            self.check_after = None
            if old:
                self.submit("disconnect", old.close)
        elif cmd == "prepare":
            self.session.prepare(request.get("mode"), request.get("white_id"), request.get("black_id"),
                                 request.get("human", "w"), request.get("minutes"))
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
                raise ValueError("Resolve the board fault and reconnect before starting")
            self.session.start(request.get("verified"))
        elif cmd == "pause":
            self.session.pause()
        elif cmd == "resume":
            if self.session.active and not self.session.paused:
                return None
            self.session.resume()
        elif cmd == "end":
            if not self.session.active and self.session.game_id:
                return None
            self.session.end(request.get("result", "*"))
        elif cmd == "hint":
            if not self.session.active or self.session.paused or not self.session.synchronized():
                raise ValueError("Resume and synchronize the current board before requesting a hint")
            self.session.maybe_search(force_hint=True)
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

    def poll_board(self):
        # 只请求对局需要的整盘数据和状态；MCU 持续独立扫描。
        result = {}
        try:
            self.link.request("SCAN", timeout=0.6)
        except DeviceError as exc:
            if str(exc) != "NOT_READY":
                raise
        result["status"] = fields(self.link.request("STATUS", timeout=0.6))
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
                elif kind == "poll":
                    if result["status"].get("armed") == "1":
                        # This UI is manual-board only; disarm a leftover bench session.
                        self.submit("stop", lambda: self.link.request("STOP", timeout=0.6))
            except Exception as exc:
                self.notice = f"Board communication failed: {exc}"
                self.check_after = None
                if self.link:
                    old, self.link = self.link, None
                    try:
                        old.close()
                    except Exception:
                        pass
                self.session.connection(False)
        if self.link:
            if self.link._failure:
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
                        if frame.kind == "BOARD":
                            raw = int(frame.payload, 16)
                            self.session.on_board(raw)
                            if self.check_after is not None and self.session.board_generation > self.check_after:
                                self.session.check()
                                self.check_after = None
                        elif frame.kind == "EVENT":
                            self.session.event(frame.payload)
                        elif frame.kind == "HELLO":
                            self.session.ready = False
                            if self.session.active:
                                self.session.pause("Board restarted. Check the current position before resuming.")
                        elif frame.kind == "FAULT":
                            self.fault = frame.payload
                            self.session.ready = False
                            if self.session.active:
                                self.session.pause(f"Board fault: {frame.payload}")
                    except Exception as exc:
                        self.notice = str(exc)
                if not self.job and now - self.last_poll >= 1.0:
                    self.last_poll = now
                    self.submit("poll", self.poll_board)
        self.session.tick()
        if self.session.active and not self.session.paused:
            self.session.maybe_search()

    def state(self):
        # 只返回游戏与连接状态；UI 不提供独立诊断和 LED 调试功能。
        state = self.session.state()
        age = None if self.session.board_at is None else max(0, round((self.now() - self.session.board_at) * 1000))
        state.update({"type": "state", "board_connected": self.link is not None,
                      "board_known": self.session.fresh(),
                      "board": f"{self.session.mask:016X}" if self.session.mask is not None and self.session.fresh() else None,
                      "board_age_ms": age, "port": self.port, "ports": self.available_ports,
                      "usb_busy": self.job is not None, "check_pending": self.check_after is not None,
                      "fault": self.fault, "error": self.notice,
                      "engine_error": self.session.hint_error})
        return state

    def controller_lost(self):
        if self.session.active and not self.session.paused:
            self.session.tick_clock_only()
            self.session.pause("UI disconnected. Reconnect and resume when ready.")

    def close(self):
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

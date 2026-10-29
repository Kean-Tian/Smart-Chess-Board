"""Pi-side USB client. This module never opens Raspberry Pi GPIO lines."""
from __future__ import annotations

import queue
import secrets
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    kind: str
    request_id: int | None
    payload: str


def parse_frame(line: str) -> Frame:
    parts = line.strip().split(maxsplit=2)
    if not parts:
        raise ValueError("Empty frame")
    kind = parts[0]
    if kind in {"ACK", "ERR", "DONE", "STATUS"}:
        if len(parts) < 3 or not parts[1].isdigit():
            raise ValueError("Malformed reply")
        return Frame(kind, int(parts[1]), parts[2])
    if kind in {"BOARD", "RAW"}:
        if len(parts) != 2 or len(parts[1]) != 16:
            raise ValueError("Malformed occupancy frame")
        int(parts[1], 16)
        return Frame(kind, None, parts[1])
    if kind in {"EVENT", "FAULT", "HELLO"}:
        return Frame(kind, None, line.strip()[len(kind):].strip())
    raise ValueError("Unknown frame")


class DeviceError(RuntimeError):
    pass


class ScbLink:
    """One reader owns the serial port; replies are correlated by request ID.

    Motion is never retried automatically. Timeout sends STOP and raises.
    A heartbeat maintains the MCU watchdog, but never arms the motors itself.
    """

    def __init__(self, serial_port):
        self.serial = serial_port
        self.events = queue.Queue(maxsize=128)
        self.board: int | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending = {}
        self._counter = secrets.randbelow(1_000_000_000) + 1
        self._failure: Exception | None = None
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._heartbeat = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._reader.start()
        try:
            self.request("PING", timeout=3)
        except Exception:
            self.close()
            raise
        self._heartbeat.start()

    @classmethod
    def open(cls, port="/dev/ttyACM0"):
        import serial  # pyserial is required only for a real connection.
        device = serial.Serial(port, baudrate=115200, timeout=0.1, write_timeout=1)
        device.reset_input_buffer()
        return cls(device)

    def _write(self, command, request_id):
        if not command or any(c in command for c in "\r\n\x00"):
            raise ValueError("Command must be one ASCII line")
        payload = f"@{request_id} {command}\n".encode("ascii")
        if len(payload) > 127:
            raise ValueError("Command too long")
        with self._write_lock:
            if self._failure:
                raise DeviceError(str(self._failure))
            if self.serial.write(payload) != len(payload):
                raise DeviceError("Incomplete serial write")

    def _next_id(self):
        with self._lock:
            self._counter = self._counter % 2_000_000_000 + 1
            return self._counter

    def _fire(self, command):
        self._write(command, self._next_id())

    def _read_loop(self):
        # Serial timeouts may split lines. Preserve fragments until newline.
        fragment = bytearray()
        discard = False
        try:
            while not self._stop.is_set():
                chunk = self.serial.read(256)
                for byte in chunk:
                    if byte != 10:
                        if not discard:
                            fragment.append(byte)
                            if len(fragment) > 512:
                                fragment.clear()
                                discard = True
                        continue
                    if discard:
                        discard = False
                        continue
                    try:
                        frame = parse_frame(fragment.decode("ascii"))
                    except (ValueError, UnicodeError):
                        fragment.clear()
                        continue
                    fragment.clear()
                    if frame.request_id is not None:
                        with self._lock:
                            pending = self._pending.get(frame.request_id)
                        if pending:
                            pending.put(frame)
                    else:
                        if frame.kind == "BOARD":
                            self.board = int(frame.payload, 16)
                        try:
                            self.events.put_nowait(frame)
                        except queue.Full:
                            try:
                                self.events.get_nowait()
                            except queue.Empty:
                                pass
                            self.events.put_nowait(frame)
        except Exception as exc:
            if not self._stop.is_set():
                self._failure = exc
                with self._lock:
                    for pending in self._pending.values():
                        pending.put(Frame("ERR", None, "DISCONNECTED"))

    def _heartbeat_loop(self):
        while not self._stop.wait(0.5):
            try:
                self._fire("PING")
            except Exception as exc:
                self._failure = exc
                return  # MCU independently disarms after its heartbeat timeout.

    def request(self, command, timeout=2.0, wait_done=False):
        request_id = self._next_id()
        pending = queue.Queue()
        with self._lock:
            self._pending[request_id] = pending
        try:
            self._write(command, request_id)
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty
                frame = pending.get(timeout=remaining)
                if frame.kind == "ERR":
                    raise DeviceError(frame.payload)
                if frame.kind == "DONE" or (not wait_done and frame.kind in {"ACK", "STATUS"}):
                    return frame
        except queue.Empty as exc:
            # Never replay an uncertain movement request.
            try:
                self._fire("STOP")
            except Exception:
                pass
            raise TimeoutError(f"MCU reply timed out: {command}") from exc
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def goto(self, square, timeout=30):
        return self.request(f"GOTO {square}", timeout=timeout, wait_done=True)

    def move(self, source, destination, timeout=30):
        """Bench-level X-then-Y transport. DONE confirms pulses, not physical success."""
        return self.request(f"MOVE {source} {destination}", timeout=timeout, wait_done=True)

    def close(self):
        if self._stop.is_set():
            return
        try:
            self._fire("STOP")
        except Exception:
            pass
        self._stop.set()
        self._reader.join(timeout=0.5)
        if self._heartbeat.is_alive():
            self._heartbeat.join(timeout=0.5)
        self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Smart Chess Board USB terminal")
    parser.add_argument("--port", default="/dev/ttyACM0")
    args = parser.parse_args()
    with ScbLink.open(args.port) as link:
        print("Connected. Outputs start DISARMED. Enter STATUS, SCAN, LED a1 20 0 0, or quit.")
        while True:
            try:
                command = input("SCB > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if command.lower() == "quit":
                break
            if not command:
                continue
            try:
                is_motion = command.split()[0] in {"MOVE", "GOTO", "JOG"}
                print(link.request(command, timeout=30 if is_motion else 2, wait_done=is_motion))
                while not link.events.empty():
                    print(link.events.get_nowait())
            except (DeviceError, TimeoutError, ValueError) as exc:
                print(exc)

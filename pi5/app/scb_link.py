"""Pi-side USB client. This module never opens Raspberry Pi GPIO lines."""
from __future__ import annotations

import queue
import secrets
import select
import sys
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    kind: str
    request_id: int | None
    payload: str


# Decode one MCU protocol line into a reply or an unsolicited event.
def parse_frame(line: str) -> Frame:
    parts = line.strip().split(maxsplit=2)
    if not parts:
        raise ValueError("Empty frame")
    kind = parts[0]
    if kind in {"ACK", "ERR", "DONE", "STATUS", "TIMING", "PLATFORM"}:
        if len(parts) < 3 or not parts[1].isdigit():
            raise ValueError("Malformed reply")
        return Frame(kind, int(parts[1]), parts[2])
    if kind in {"BOARD", "RAW"}:
        if len(parts) != 2 or len(parts[1]) != 16:
            raise ValueError("Malformed occupancy frame")
        int(parts[1], 16)
        return Frame(kind, None, parts[1])
    if kind in {"EVENT", "FAULT", "HELLO", "SENSOR"}:
        return Frame(kind, None, line.strip()[len(kind):].strip())
    raise ValueError("Unknown frame")


# Convert the wire mask to readable logical squares; this does not calibrate physical orientation.
def format_occupancy(payload: str) -> str:
    if len(payload) != 16 or any(ch not in "0123456789abcdefABCDEF" for ch in payload):
        raise ValueError("Invalid occupancy mask")
    mask = int(payload, 16)
    if mask == 0:
        return "Empty"
    if mask == (1 << 64) - 1:
        return "All 64 squares"
    return ", ".join(f"{chr(ord('a') + square % 8)}{square // 8 + 1}"
                     for square in range(64) if mask & (1 << square))


# Format replies and sensor events for the terminal without changing the wire protocol.
def format_frame(frame: Frame) -> str:
    if frame.kind in {"BOARD", "RAW"}:
        try:
            label = "BOARD" if frame.kind == "BOARD" else "RAW (before debounce)"
            return f"{label} | OCCUPY={format_occupancy(frame.payload)}"
        except ValueError:
            pass
    if frame.kind == "SENSOR":
        try:
            fields = dict(token.split("=", 1) for token in frame.payload.split())
            pins = [fields[name].split(":", 1) for name in ("A0", "A1", "A2")]
            gpio = ",".join(pin for pin, _ in pins)
            levels = "".join(level for _, level in pins)
            return (f"MUX(A2,A1,A0)={fields['mux']} [GPIO{gpio}={levels}] | "
                    f"INPUTS(DIG_OUT1..8)={fields['inputs']} | "
                    f"OCCUPY={format_occupancy(fields['occupy'])} | frame={fields['frame']}")
        except (ValueError, KeyError):
            pass
    if frame.kind == "ACK":
        return f"ACK | Request ID={frame.request_id} | Command={frame.payload}"
    if frame.kind == "DONE":
        return f"Motion pulses completed | Request ID={frame.request_id} | Details={frame.payload}"
    if frame.kind in {"STATUS", "TIMING", "PLATFORM"}:
        return f"{frame.kind} | Request ID={frame.request_id} | {frame.payload}"
    if frame.kind == "EVENT":
        return f"Board event | {frame.payload}"
    if frame.kind == "HELLO":
        return f"Board startup | Board ID and protocol version={frame.payload}"
    if frame.kind in {"ERR", "FAULT"}:
        label = "Command error" if frame.kind == "ERR" else "Device fault"
        return f"{label} | Reason code={frame.payload}"
    return f"Message type={frame.kind} | Payload={frame.payload}"


def format_scan_timing(frame: Frame, reply_ms: float) -> str:
    """Format MCU frame statistics separately from the host SCAN round trip."""
    if frame.kind != "TIMING":
        raise ValueError("Expected a TIMING reply")
    fields = dict(token.split("=", 1) for token in frame.payload.split())
    values = {name: int(fields[name])
              for name in ("frame_us", "max_us", "debounce_us", "misses")}
    if any(value < 0 for value in values.values()):
        raise ValueError("Negative timing counter")

    def milliseconds(name):
        return f"{values[name] / 1000:.3f} ms" if values[name] else "not recorded yet"

    return (f"SCAN timing | Last full-board period={milliseconds('frame_us')} | "
            f"Maximum period={milliseconds('max_us')}\n"
            f"Latency | Debounce confirmation={milliseconds('debounce_us')} | "
            f"SCAN round trip={reply_ms:.3f} ms | Scan overruns={values['misses']}")


def print_scan_report(link):
    """Query the cached board, then query existing MCU timing diagnostics.

    The host duration ends at SCAN ACK and excludes the separate TIMING request.
    It includes OS/USB/UART/MCU queueing; it is not physical detection latency.
    """
    started = time.monotonic()
    reply = link.request("SCAN")
    reply_ms = (time.monotonic() - started) * 1000
    print(format_frame(reply), flush=True)
    try:
        timing = link.request("TIMING")
        print(format_scan_timing(timing, reply_ms), flush=True)
    except (DeviceError, TimeoutError, ValueError, KeyError) as exc:
        # A failed timing query must not replace an already successful SCAN.
        print(f"SCAN round trip={reply_ms:.3f} ms | Scan statistics unavailable: {exc}", flush=True)


class DeviceError(RuntimeError):
    pass


class ScbLink:
    """One reader owns the serial port; replies are correlated by request ID.

    Motion is never retried automatically. Timeout sends STOP and raises.
    A heartbeat maintains the MCU watchdog, but never arms the motors itself.
    """

    # Start serial reception, check PING, then start the background heartbeat.
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
    # Open the USB-UART port at 115200 baud and allow reset transients to settle.
    def open(cls, port="/dev/ttyUSB0", *, exclusive=False):
        import serial  # pyserial is required only for a real connection.
        # Saola USB-UART DTR/RTS control EN/GPIO0. Set inactive states before
        # opening; allow any driver-generated reset transient to settle.
        device = serial.Serial(baudrate=115200, timeout=0.1, write_timeout=1)
        if exclusive:
            device.exclusive = True
        device.dtr = False
        device.rts = False
        device.port = port
        try:
            device.open()
            time.sleep(0.5)
            device.reset_input_buffer()
            return cls(device)
        except BaseException:
            device.close()
            raise

    # Send one ASCII command line with a request ID; serialize concurrent writes.
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

    # Reassemble serial lines, match replies by ID and queue asynchronous board events.
    def _read_loop(self):
        # Serial timeouts may split lines. Preserve fragments until newline.
        fragment = bytearray()
        discard = False
        try:
            while not self._stop.is_set():
                # Block for one byte, then drain only bytes already buffered. Small
                # BOARD/reply lines must not wait for a 256-byte read to time out.
                waiting = getattr(self.serial, "in_waiting", 0)
                chunk = self.serial.read(min(256, max(1, waiting)))
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

    # Send PING every 0.5 seconds so the MCU can detect a lost control link.
    def _heartbeat_loop(self):
        while not self._stop.wait(0.5):
            try:
                self._fire("PING")
            except Exception as exc:
                self._failure = exc
                return  # MCU independently disarms after its heartbeat timeout.

    # Wait for this command reply; on timeout send STOP without replaying motion.
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
                if frame.kind == "DONE" or (not wait_done and frame.kind in {"ACK", "STATUS", "TIMING", "PLATFORM"}):
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

    # Send STOP, finish the background workers and release the serial port.
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
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Actual serial port of the development board")
    args = parser.parse_args()
    with ScbLink.open(args.port) as link:
        print("Connected. Enter STATUS, SCAN, RAW, INPUTS, or quit.")
        print("Board and occupied-row sensor updates appear automatically.")
        try:
            print_scan_report(link)
        except (DeviceError, TimeoutError) as exc:
            print(exc)
        print("SCB > ", end="", flush=True)
        while True:
            try:
                # Keep draining sensor events while waiting for a command,
                # instead of hiding placement/lift updates until Enter is pressed.
                if not link.events.empty():
                    print()
                    while not link.events.empty():
                        print(format_frame(link.events.get_nowait()), flush=True)
                    print("SCB > ", end="", flush=True)
                if not select.select([sys.stdin], [], [], 0.05)[0]:
                    continue
                command = input().strip()
            except (EOFError, KeyboardInterrupt):
                break
            if command.lower() == "quit":
                break
            if not command:
                print("SCB > ", end="", flush=True)
                continue
            try:
                if command == "SCAN":
                    print_scan_report(link)
                else:
                    is_motion = command.split()[0] in {"MOVE", "GOTO", "JOG"}
                    print(format_frame(link.request(command, timeout=30 if is_motion else 2,
                                                   wait_done=is_motion)))
            except (DeviceError, TimeoutError, ValueError) as exc:
                print(exc)
            print("SCB > ", end="", flush=True)

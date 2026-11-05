import queue
import re
import sys
import unittest
import types
import subprocess
import time
import os
import select
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from scb_link import ScbLink, DeviceError, parse_frame, format_frame

SENSOR_LINE = (b"SENSOR frame=2 mux=000 A0=36:0 A1=37:0 A2=38:0 "
               b"inputs=00000001 occupy=0000000000000080 polarity=HIGH\n")


class FakeSerial:
    def __init__(self):
        self.incoming = queue.Queue()
        self.written = []
        self.closed = False

    def write(self, packet):
        self.written.append(packet)
        match = re.fullmatch(rb"@(\d+) (.+)\n", packet)
        request_id, command = match.groups()
        if command == b"FAIL":
            self.incoming.put(b"ERR " + request_id + b" INVALID\n")
        elif command == b"IGNORE":
            pass
        elif command.startswith(b"MOVE"):
            self.incoming.put(b"ACK " + request_id + b" MOTION\n")
            self.incoming.put(b"DONE " + request_id + b" MOTION\n")
        else:
            # Exercise partial-frame input and unsolicited occupancy.
            self.incoming.put(b"BOARD 0000000000000080\n" + SENSOR_LINE + b"ACK ")
            self.incoming.put(request_id + b" " + command + b"\n")
        return len(packet)

    def read(self, count):
        try:
            return self.incoming.get(timeout=0.02)
        except queue.Empty:
            return b""

    def close(self):
        self.closed = True


class LinkTests(unittest.TestCase):
    def test_frames(self):
        self.assertEqual(parse_frame("DONE 5 MOTION").request_id, 5)
        self.assertEqual(parse_frame("BOARD 0000000000000001").payload, "0000000000000001")
        for bad in ["", "BOARD ZZZZZZZZZZZZZZZZ", "BOARD 1", "ACK BAD PING", "boot text"]:
            with self.assertRaises(ValueError):
                parse_frame(bad)

    def test_sensor_trace_is_readable_and_keeps_input_order(self):
        frame = parse_frame(SENSOR_LINE.decode())
        self.assertEqual((frame.kind, frame.request_id), ("SENSOR", None))
        self.assertEqual(format_frame(frame),
                         "MUX(A2,A1,A0)=000 [GPIO36,37,38=000] | "
                         "INPUTS(DIG_OUT1..8)=00000001 | "
                         "OCCUPY=h1 | frame=2")
        malformed = parse_frame("SENSOR incomplete")
        self.assertEqual(format_frame(malformed), str(malformed))
        board = parse_frame("BOARD 0000000000000080")
        self.assertEqual(format_frame(board), "BOARD | OCCUPY=h1")
        for payload, expected in [
                ("0000000000000000", "无棋子"),
                ("0000000000000001", "a1"),
                ("8000000000000081", "a1, h1, h8"),
                ("FFFFFFFFFFFFFFFF", "全部64格")]:
            with self.subTest(payload=payload):
                self.assertEqual(format_frame(parse_frame(f"BOARD {payload}")),
                                 f"BOARD | OCCUPY={expected}")
                self.assertEqual(format_frame(parse_frame(f"RAW {payload}")),
                                 f"RAW | OCCUPY={expected}")

    def test_live_sensor_updates_do_not_wait_for_keyboard_input(self):
        root = Path(__file__).resolve().parents[2]
        script = f'''
import runpy, sys, threading, types
from pathlib import Path
root = Path({str(root)!r})
sys.path.insert(0, str(root / "pi5/tests"))
from scb_link_tests import FakeSerial
class Port(FakeSerial):
    def __init__(self, **kwargs):
        super().__init__()
    def open(self):
        def changed():
            self.incoming.put(b"SENSOR frame=777 mux=001 A0=36:1 A1=37:0 A2=38:0 inputs=10000000 occupy=0000000000000100 polarity=HIGH\\n")
        timer = threading.Timer(0.9, changed)
        timer.daemon = True
        timer.start()
    def reset_input_buffer(self):
        pass
sys.modules["serial"] = types.SimpleNamespace(Serial=Port)
sys.argv = ["scb_link.py", "--port", "fake"]
runpy.run_path(str(root / "pi5/app/scb_link.py"), run_name="__main__")
'''
        process = subprocess.Popen([sys.executable, "-u", "-c", script],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        try:
            # Supply no keyboard input while the late sensor event arrives.
            output = ""
            deadline = time.monotonic() + 5
            while "frame=777" not in output and time.monotonic() < deadline:
                if select.select([process.stdout], [], [], 0.1)[0]:
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        break
                    output += chunk.decode("utf-8")
            tail, errors = process.communicate("quit\n", timeout=5)
            output += tail
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        self.assertEqual(process.returncode, 0, errors)
        self.assertIn("MUX(A2,A1,A0)=001", output, errors)
        self.assertIn("[GPIO36,37,38=100]", output)
        self.assertIn("OCCUPY=a2 | frame=777", output)

    def test_connection_motion_and_error(self):
        fake = FakeSerial()
        with ScbLink(fake) as link:
            self.assertEqual(link.board, 0x80)
            self.assertTrue(any(frame.kind == "SENSOR" for frame in list(link.events.queue)))
            self.assertEqual(link.request("SCAN").kind, "ACK")
            self.assertEqual(link.move("e2", "e4").kind, "DONE")
            with self.assertRaises(DeviceError):
                link.request("FAIL")
            with self.assertRaises(ValueError):
                link.request("PING\nARM")
        self.assertTrue(fake.closed)

    def test_usb_uart_open_deasserts_control_lines_before_open(self):
        device = Mock()
        def opened():
            self.assertFalse(device.dtr)
            self.assertFalse(device.rts)
            self.assertEqual(device.port, "test-uart-port")
        device.open.side_effect = opened
        factory = Mock(return_value=device)
        with patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=factory)}), \
                patch("scb_link.time.sleep") as settle, \
                patch.object(ScbLink, "__init__", return_value=None) as initialize:
            ScbLink.open("test-uart-port")
        factory.assert_called_once_with(baudrate=115200, timeout=0.1, write_timeout=1)
        settle.assert_called_once_with(0.5)
        device.reset_input_buffer.assert_called_once()
        initialize.assert_called_once_with(device)

    def test_usb_uart_open_failure_closes_device(self):
        device = Mock()
        device.open.side_effect = OSError("unavailable")
        with patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=Mock(return_value=device))}):
            with self.assertRaises(OSError):
                ScbLink.open("test-uart-port")
        device.close.assert_called_once()

    def test_timeout_stops_without_replay(self):
        fake = FakeSerial()
        with ScbLink(fake) as link:
            with self.assertRaises(TimeoutError):
                link.request("IGNORE", timeout=0.05)
            self.assertEqual(sum(b" IGNORE\n" in line for line in fake.written), 1)
            self.assertTrue(any(b" STOP\n" in line for line in fake.written))


if __name__ == "__main__":
    unittest.main()

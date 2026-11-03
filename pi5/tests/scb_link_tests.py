import queue
import re
import sys
import unittest
import types
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from scb_link import ScbLink, DeviceError, parse_frame


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
            self.incoming.put(b"BOARD 0000000000000001\nACK ")
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

    def test_connection_motion_and_error(self):
        fake = FakeSerial()
        with ScbLink(fake) as link:
            self.assertEqual(link.board, 1)
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

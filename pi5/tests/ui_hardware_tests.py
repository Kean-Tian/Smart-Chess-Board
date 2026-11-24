"""Motion/fault/LED integration with real rules and SQLite, simulated MCU only."""
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from board_game import expected_occupancy
from game_store import GameStore
from scb_link import Frame
from ui_game import START_OCCUPANCY
from ui_service import UiCore
from ui_hardware import execute_motion


class Mcu:
    _failure = None
    def __init__(self):
        self.events = queue.Queue()
        self.commands = []
        self.mask = START_OCCUPANCY
        self.fault = "NONE"
        self.calibrated = True
        self.finish = threading.Event()
        self.entered = threading.Event()
        self.finish.set()
        self.motion_reply = "DONE"

    def request(self, cmd, **kwargs):
        self.commands.append(cmd)
        if cmd == "STATUS":
            return Frame("STATUS", 1, f"armed=0 moving=0 magnet=0 origin={int(self.calibrated)} steps=10 fault={self.fault}")
        if cmd == "SNAPSHOT":
            return Frame("SNAPSHOT", 1, f"occupy={self.mask:016X} frame=100 fault={self.fault}")
        if cmd == "CLEAR_FAULT":
            self.fault = "NONE"
        if cmd.startswith("MOVE "):
            self.entered.set()
            if not self.finish.wait(2):
                raise TimeoutError("Simulated motion timeout")
            return Frame(self.motion_reply, 1, "MOVE")
        if cmd.startswith("GOTO "):
            return Frame("DONE", 1, "GOTO")
        if cmd == "STOP":
            self.finish.set()
        if cmd == "SCAN":
            self.events.put(Frame("BOARD", None, f"{self.mask:016X}"))
        return Frame("ACK", 1, cmd)

    def close(self):
        self.finish.set()


class HardwareFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = GameStore(Path(self.temp.name) / "players.sqlite3")
        self.store.db.executescript("INSERT INTO players(name) VALUES('White'); INSERT INTO players(name) VALUES('Black');")
        self.link = Mcu()
        self.core = UiCore(self.store, link_factory=lambda _: self.link, automatic_motion=True)
        self.core.link = self.link
        self.core.last_ports = self.core.last_poll = self.core.now()
        self.s = self.core.session
        self.s.connection(True)

    def tearDown(self):
        self.link.finish.set()
        self.core.close()
        self.store.close()
        self.temp.cleanup()

    def start(self, mode="pvp"):
        self.s.prepare(mode, 1, 2, "w", 0, True)
        self.s.on_board(START_OCCUPANCY)
        self.s.check()
        self.s.start(True)

    def update_until(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.core.update()
            if predicate(): return
            time.sleep(.005)
        self.fail(f"Timed out: {self.core.state()}")

    def leds(self, command):
        self.update_until(lambda: self.core.led_sent == command and not self.core.led_job)

    def computer_turn(self):
        self.start("pvc")
        self.s.maybe_search = lambda **_: None
        self.s.on_board(expected_occupancy(self.s.game.fen(), "e2e4"))
        self.s.commit("e2e4", explicit=True)
        self.s.computer_move = "e7e5"
        self.link.mask = self.s.mask

    def test_led_guidance_accepted_illegal_restore_and_end(self):
        self.start()
        self.leds("LED_CLEAR")
        self.s.on_board(START_OCCUPANCY & ~(1 << 12))
        self.s.event("LIFT e2")
        self.leds("GUIDE 0000000010100000")
        self.assertEqual(self.s.legal_destinations, ["e3", "e4"])
        self.s.on_board(START_OCCUPANCY)
        self.leds("LED_CLEAR")
        self.s.on_board(expected_occupancy(self.s.game.fen(), "e2e4"))
        self.s.event("MOVE e2e4")
        self.leds("MARK e2 e4 LEGAL")
        self.s.on_board(self.s.mask)  # A periodic SCAN must not erase accepted feedback.
        self.assertEqual(self.s.feedback_command, "MARK e2 e4 LEGAL")
        accepted = self.s.mask
        self.s.on_board(accepted ^ (1 << 52) ^ (1 << 28))
        self.s.event("MOVE e7e4")
        self.leds("MARK e7 e4 ILLEGAL")
        self.s.event("LIFT d7")
        self.s.set_guidance(False)
        self.assertEqual(self.s.feedback_command, "MARK e7 e4 ILLEGAL")
        self.assertEqual(self.s.game.move_history, ["e2e4"])
        self.s.on_board(accepted)
        self.leds("LED_CLEAR")
        self.s.end()
        self.assertEqual(self.s.feedback_command, "LED_CLEAR")

    def test_motion_waits_for_done_and_fresh_matching_snapshot(self):
        self.computer_turn()
        target = expected_occupancy(self.s.game.fen(), "e7e5")
        self.link.finish.clear()
        self.core.handle({"cmd": "execute_computer", "move": "e7e5"})
        self.assertTrue(self.link.entered.wait(1))
        self.s.on_board(target)
        self.s.event("MOVE e7e5")
        with self.assertRaises(ValueError): self.s.commit("e7e5", explicit=True)
        self.assertEqual(self.s.game.move_history, ["e2e4"])
        self.assertNotIn("SNAPSHOT", self.link.commands)
        self.link.mask = target
        # A queued old frame cannot undo the post-motion snapshot.
        self.link.events.put(Frame("BOARD", None, f"{START_OCCUPANCY:016X}"))
        self.link.finish.set()
        self.update_until(lambda: self.core.motion_job is None)
        self.assertEqual(self.s.game.move_history, ["e2e4", "e7e5"])
        self.assertEqual(self.s.mask, target)
        self.assertFalse(self.s.motion_active)
        self.assertLess(self.link.commands.index("MOVE e7 e5"), self.link.commands.index("SNAPSHOT"))

    def test_motion_wrong_final_board_pauses_without_commit(self):
        self.computer_turn()
        self.core.handle({"cmd": "execute_computer", "move": "e7e5"})
        self.update_until(lambda: self.core.motion_job is None)
        self.assertTrue(self.s.paused)
        self.assertIn("mismatch", self.core.fault)
        self.assertEqual(self.s.game.move_history, ["e2e4"])

    def test_reconnect_does_not_clear_fault_explicit_reset_then_resume(self):
        self.start()
        self.core.latch_fault("MOTION_TIMEOUT")
        self.core.handle({"cmd": "disconnect"})
        self.update_until(lambda: self.core.job is None)
        self.core.handle({"cmd": "connect", "port": "/dev/test"})
        self.update_until(lambda: self.core.link is not None)
        self.assertTrue(self.core.fault)
        self.assertTrue(self.s.paused)
        with self.assertRaises(ValueError): self.core.handle({"cmd": "resume"})
        self.update_until(lambda: not self.core.job)
        self.core.handle({"cmd": "reset_fault"})
        self.update_until(lambda: not self.core.job)
        self.assertFalse(self.core.fault)
        self.assertTrue(self.s.paused)  # Reset does not restart clocks/play.
        self.core.handle({"cmd": "resume"})
        self.update_until(lambda: not self.core.job)
        self.assertFalse(self.s.paused)

    def test_fault_during_motion_sends_stop_and_ignores_late_done(self):
        self.computer_turn()
        self.link.finish.clear()
        self.core.handle({"cmd": "execute_computer", "move": "e7e5"})
        self.assertTrue(self.link.entered.wait(1))
        self.link.events.put(Frame("FAULT", None, "MOTION_TIMEOUT"))
        self.update_until(lambda: self.core.motion_job is None)
        self.assertIn("STOP", self.link.commands)
        self.assertEqual(self.s.game.move_history, ["e2e4"])
        self.assertTrue(self.s.paused)
        self.assertTrue(self.core.fault)

    def test_no_runtime_opt_in_and_no_calibration_block_motion(self):
        self.computer_turn()
        self.core.automatic_motion = False
        with self.assertRaises(ValueError): self.core.handle({"cmd": "execute_computer", "move": "e7e5"})
        self.assertNotIn("ARM", self.link.commands)
        self.core.automatic_motion = True
        self.link.calibrated = False
        self.core.handle({"cmd": "execute_computer", "move": "e7e5"})
        self.update_until(lambda: self.core.motion_job is None)
        self.assertNotIn("ARM", self.link.commands)
        self.assertTrue(self.core.fault)

    def test_ack_is_not_motion_completion(self):
        self.link.motion_reply = "ACK"
        with self.assertRaisesRegex(ValueError, "completion"):
            execute_motion(self.link, "e2e4", threading.Event())
        self.assertIn("STOP", self.link.commands)
        self.assertNotIn("SNAPSHOT", self.link.commands)

    def test_clock_or_internal_pause_stops_motion(self):
        self.computer_turn()
        self.link.finish.clear()
        self.core.handle({"cmd": "execute_computer", "move": "e7e5"})
        self.assertTrue(self.link.entered.wait(1))
        self.s.pause("Time expired")
        self.update_until(lambda: self.core.motion_job is None)
        self.assertIn("STOP", self.link.commands)
        self.assertEqual(self.s.game.move_history, ["e2e4"])


if __name__ == "__main__": unittest.main()

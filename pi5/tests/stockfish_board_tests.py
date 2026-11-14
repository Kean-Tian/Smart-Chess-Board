import sys
import unittest
import threading
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from board_game import PhysicalGame, occupancy, fen_board, expected_occupancy
from scb_rules import Game


class Link:
    def __init__(self): self.commands = []
    def request(self, command, **kwargs): self.commands.append(command)


class Engine:
    def best_move(self, fen, legal, movetime, history):
        assert "e7e5" in legal
        return "e7e5"


class BoardEngineTests(unittest.TestCase):
    def start_game(self, game):
        link = Link()
        manager = PhysicalGame(game, link, lambda *_: None, engine=Engine())
        self.addCleanup(manager.close)
        manager.on_board(occupancy(fen_board(game.fen())))
        manager.on_board(expected_occupancy(game.fen(), "e2e4"))
        self.assertTrue(manager.try_move("e2e4"))
        return manager, link

    def test_engine_move_waits_for_physical_confirmation(self):
        with Game() as game:
            manager, link = self.start_game(game)
            before = game.fen()
            manager.maybe_computer_turn()
            manager._search.result(timeout=1)
            manager.maybe_computer_turn()
            self.assertEqual(game.fen(), before)
            self.assertEqual(manager.computer_move, "e7e5")
            self.assertEqual(link.commands[-2:], ["LED_CLEAR", "LED e7 0 0 20"])
            # BOARD occupancy alone can reveal a lift even if EVENT LIFT is lost.
            manager.on_board(occupancy(fen_board(before)) & ~(1 << 52))
            self.assertEqual(link.commands[-1], "LED e5 0 20 0")
            self.assertEqual(game.fen(), before)
            self.assertFalse(any(cmd.startswith(("ARM", "MOVE", "GOTO")) for cmd in link.commands))
            manager.on_board(expected_occupancy(game.fen(), "e7e5"))
            self.assertTrue(manager.try_move("e7e5"))
            self.assertEqual(game.move_history, ["e2e4", "e7e5"])
            self.assertEqual(game.fen().split()[1], "w")
            self.assertIsNone(manager.guidance.move)

    def test_wrong_computer_move_requires_restoring_board(self):
        with Game() as game:
            manager, link = self.start_game(game)
            manager.maybe_computer_turn()
            manager._search.result(timeout=1)
            manager.maybe_computer_turn()
            before = game.fen()
            manager.on_board(expected_occupancy(game.fen(), "e7e6"))
            self.assertFalse(manager.try_move("e7e6"))
            self.assertEqual(game.fen(), before)
            self.assertTrue(manager.restore_required)
            self.assertIsNone(manager.guidance.move)
            manager.on_board(occupancy(fen_board(game.fen())))
            self.assertFalse(manager.restore_required)
            self.assertEqual(manager.computer_move, "e7e5")
            self.assertEqual(link.commands[-2:], ["LED_CLEAR", "LED e7 0 0 20"])

    def test_waiting_for_engine_move_shows_destination_without_further_board_events(self):
        with Game() as game:
            manager, link = self.start_game(game)
            now = [0.0]
            manager.guidance._clock = lambda: now[0]
            manager.maybe_computer_turn()
            manager._search.result(timeout=1)
            manager.maybe_computer_turn()
            before = game.fen()
            now[0] = 5.0
            manager.update_guidance()
            self.assertEqual(link.commands[-1], "LED e5 0 20 0")
            self.assertEqual(game.fen(), before)
            now[0] = 5.5
            manager.update_guidance()
            self.assertEqual(link.commands[-1], "LED e5 0 0 0")

    def test_search_does_not_block_sensor_events_or_use_live_rules_in_worker(self):
        ready, release = threading.Event(), threading.Event()
        class SlowEngine:
            def best_move(self, fen, legal, movetime, history):
                assert isinstance(fen, str) and isinstance(legal, tuple) and isinstance(history, tuple)
                ready.set()
                if not release.wait(2):
                    raise RuntimeError("test did not release search")
                return "e7e5"
        with Game() as game:
            manager, link = self.start_game(game)
            manager.engine = SlowEngine()
            started = time.monotonic()
            manager.maybe_computer_turn()
            self.assertLess(time.monotonic() - started, 0.1)
            self.assertTrue(ready.wait(1))
            try:
                # Input remains processable before the search has returned.
                lifted = occupancy(fen_board(game.fen())) & ~(1 << 52)
                manager.on_board(lifted)
                self.assertEqual(manager.mask, lifted)
                manager.maybe_computer_turn()
                self.assertIsNone(manager.computer_move)
                self.assertFalse(manager._search.done())
            finally:
                release.set()
            manager._search.result(timeout=1)
            manager.maybe_computer_turn()
            self.assertIsNone(manager.computer_move)  # Board still incomplete.
            manager.on_board(occupancy(fen_board(game.fen())))
            manager.maybe_computer_turn()
            self.assertEqual(manager.computer_move, "e7e5")


if __name__ == "__main__":
    unittest.main()

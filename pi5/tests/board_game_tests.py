import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from board_game import PhysicalGame, expected_occupancy, occupancy, fen_board
from move_guidance import MoveGuidance

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        class Link:
            def __init__(self): self.commands = []
            def request(self, command, **kwargs): self.commands.append(command)
        self.link = Link()
        self.now = 0.0
        self.guide = MoveGuidance(self.link, clock=lambda: self.now)
        self.mask = occupancy(fen_board(START))

    def test_five_second_fallback_and_blink_without_sensor_changes(self):
        self.guide.start("e2e4", self.mask)
        self.assertEqual(self.link.commands, ["LED_CLEAR", "LED e2 0 0 20"])
        self.now = 4.999
        self.guide.update(self.mask)
        self.assertEqual(len(self.link.commands), 2)
        self.now = 5.0
        self.guide.update(self.mask)
        self.assertEqual(self.link.commands[-1], "LED e4 0 20 0")
        self.guide.update(self.mask)
        self.assertEqual(len(self.link.commands), 3)  # No redundant LED traffic.
        self.now = 5.5
        self.guide.update(self.mask)
        self.assertEqual(self.link.commands[-1], "LED e4 0 0 0")
        self.now = 6.0
        self.guide.update(self.mask)
        self.assertEqual(self.link.commands[-1], "LED e4 0 20 0")
        count = len(self.link.commands)
        self.now = 8.0  # A delayed poll must not send a burst of missed flashes.
        self.guide.update(self.mask)
        self.assertEqual(len(self.link.commands), count)

    def test_only_lifting_the_source_starts_destination_early(self):
        self.guide.start("e2e4", self.mask)
        self.now = 0.1
        self.guide.update(self.mask & ~(1 << 8))  # a2 is unrelated.
        self.assertEqual(len(self.link.commands), 2)
        self.guide.update(self.mask & ~(1 << 12))
        self.assertEqual(self.link.commands[-1], "LED e4 0 20 0")
        self.now = 0.6
        self.guide.update(self.mask & ~(1 << 12))
        self.assertEqual(self.link.commands[-1], "LED e4 0 0 0")

    def test_missing_sensor_baseline_still_uses_timeout(self):
        for mask in [None, 0]:
            with self.subTest(mask=mask):
                self.now = 0.0
                self.guide.start("e2e4", mask)
                count = len(self.link.commands)
                self.now = 1.0
                self.guide.update(mask)
                self.assertEqual(len(self.link.commands), count)
                self.now = 5.0
                self.guide.update(mask)
                self.assertEqual(self.link.commands[-1], "LED e4 0 20 0")

    def test_new_hint_and_clear_cancel_previous_timer(self):
        self.guide.start("e2e4", self.mask)
        self.now = 5.0
        self.guide.update(self.mask)
        self.guide.start("g1f3", self.mask)
        self.assertEqual(self.link.commands[-2:], ["LED_CLEAR", "LED g1 0 0 20"])
        count = len(self.link.commands)
        self.now = 6.0
        self.guide.update(self.mask)
        self.assertEqual(len(self.link.commands), count)
        self.guide.clear()
        self.assertEqual(self.link.commands[-1], "LED_CLEAR")
        count = len(self.link.commands)
        self.now = 20.0
        self.guide.update(0)
        self.guide.clear()
        self.assertEqual(len(self.link.commands), count)

    def test_both_mode_keeps_two_steady_lights(self):
        guide = MoveGuidance(self.link, "both", clock=lambda: self.now)
        guide.start("e2e4", self.mask)
        self.assertEqual(self.link.commands, ["MARK e2 e4 LEGAL"])
        for self.now in [0.1, 5.0, 5.5, 10.0]:
            guide.update(0)
        self.assertEqual(self.link.commands, ["MARK e2 e4 LEGAL"])
        guide.clear()
        self.assertEqual(self.link.commands[-1], "LED_CLEAR")


class BoardTests(unittest.TestCase):
    def test_special_occupancy(self):
        after = expected_occupancy(START, "e2e4")
        self.assertFalse(after & (1 << 12))
        self.assertTrue(after & (1 << 28))
        castle = "4k3/8/8/8/8/8/8/4K2R w K - 0 1"
        result = expected_occupancy(castle, "e1g1")
        self.assertEqual(result, (1 << 60) | (1 << 5) | (1 << 6))
        ep = "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1"
        result = expected_occupancy(ep, "e5d6")
        self.assertFalse(result & (1 << 35))
        self.assertTrue(result & (1 << 43))

    def test_state_only_commits_matching_board(self):
        class Game:
            played = []
            def fen(self): return START
            def legal_moves(self): return ["e2e4"]
            def play(self, move): self.played.append(move); return True
            def board_text(self): return "updated"
            def status(self): return ""
        class Link:
            commands = []
            def request(self, cmd, **kwargs): self.commands.append(cmd)
        g, link = Game(), Link()
        manager = PhysicalGame(g, link, lambda *_: None)
        manager.on_board(occupancy(fen_board(START)))
        self.assertFalse(manager.try_move("e2e4"))
        self.assertEqual(g.played, [])
        manager.on_board(expected_occupancy(START, "e2e4"))
        self.assertEqual(g.played, ["e2e4"])
        self.assertIn("MARK e2 e4 LEGAL", link.commands)

    def test_illegal_move_requires_restoration(self):
        class Game:
            def fen(self): return START
            def legal_moves(self): return ["e2e4"]
        class Link:
            def request(self, cmd, **kwargs): pass
        manager = PhysicalGame(Game(), Link(), lambda *_: None)
        manager.on_board(occupancy(fen_board(START)))
        manager.try_move("e2e5")
        self.assertTrue(manager.restore_required)
        manager.on_board(occupancy(fen_board(START)))
        self.assertFalse(manager.restore_required)


if __name__ == "__main__":
    unittest.main()

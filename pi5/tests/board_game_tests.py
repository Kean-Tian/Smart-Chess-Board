import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from board_game import PhysicalGame, expected_occupancy, occupancy, fen_board

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


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
            def request(self, cmd): self.commands.append(cmd)
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
            def request(self, cmd): pass
        manager = PhysicalGame(Game(), Link(), lambda *_: None)
        manager.on_board(occupancy(fen_board(START)))
        manager.try_move("e2e5")
        self.assertTrue(manager.restore_required)
        manager.on_board(occupancy(fen_board(START)))
        self.assertFalse(manager.restore_required)


if __name__ == "__main__":
    unittest.main()

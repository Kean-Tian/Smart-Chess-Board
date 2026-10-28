import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from board_game import PhysicalGame, occupancy, fen_board, expected_occupancy
from scb_rules import Game


class Link:
    def __init__(self): self.commands = []
    def request(self, command): self.commands.append(command)


class Engine:
    def choose(self, game, movetime):
        assert "e7e5" in game.legal_moves()
        return "e7e5"


class BoardEngineTests(unittest.TestCase):
    def start_game(self, game):
        link = Link()
        manager = PhysicalGame(game, link, lambda *_: None, engine=Engine())
        manager.on_board(occupancy(fen_board(game.fen())))
        manager.on_board(expected_occupancy(game.fen(), "e2e4"))
        self.assertTrue(manager.try_move("e2e4"))
        return manager, link

    def test_engine_move_waits_for_physical_confirmation(self):
        with Game() as game:
            manager, link = self.start_game(game)
            before = game.fen()
            manager.maybe_computer_turn()
            self.assertEqual(game.fen(), before)
            self.assertEqual(manager.computer_move, "e7e5")
            self.assertIn("MARK e7 e5 LEGAL", link.commands)
            self.assertFalse(any(cmd.startswith(("ARM", "MOVE", "GOTO")) for cmd in link.commands))
            manager.on_board(expected_occupancy(game.fen(), "e7e5"))
            self.assertTrue(manager.try_move("e7e5"))
            self.assertEqual(game.move_history, ["e2e4", "e7e5"])
            self.assertEqual(game.fen().split()[1], "w")

    def test_wrong_computer_move_requires_restoring_board(self):
        with Game() as game:
            manager, _ = self.start_game(game)
            manager.maybe_computer_turn()
            before = game.fen()
            manager.on_board(expected_occupancy(game.fen(), "e7e6"))
            self.assertFalse(manager.try_move("e7e6"))
            self.assertEqual(game.fen(), before)
            self.assertTrue(manager.restore_required)
            manager.on_board(occupancy(fen_board(game.fen())))
            self.assertFalse(manager.restore_required)
            self.assertEqual(manager.computer_move, "e7e5")


if __name__ == "__main__":
    unittest.main()

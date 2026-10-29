import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import play
import play_stockfish
from board_game import PhysicalGame, expected_occupancy, fen_board, occupancy
from openrouter_engine import OpenRouter, OpenRouterError
from scb_rules import Game
from stockfish_engine_tests import FAKE


def response(move):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": move}}]}).encode())


class PlayModeTests(unittest.TestCase):
    def setUp(self):
        self.output = contextlib.ExitStack()
        temporary = self.output.enter_context(tempfile.TemporaryDirectory())
        self.key_file = Path(temporary) / ".openrouter-key"
        self.output.enter_context(patch("api_key_store.KEY_FILE", self.key_file))
        self.output.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.output.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.addCleanup(self.output.close)

    def test_key_is_remembered_for_next_game_and_can_be_replaced(self):
        from opponents import create_openrouter
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), \
                patch("opponents.sys.stdin.isatty", return_value=True), \
                patch("opponents.getpass.getpass", return_value="dummy-first-key") as prompt:
            self.assertEqual(create_openrouter().api_key, "dummy-first-key")
            self.assertEqual(create_openrouter().api_key, "dummy-first-key")
            prompt.assert_called_once()
        self.assertEqual(self.key_file.stat().st_mode & 0o777, 0o600)
        with patch("opponents.getpass.getpass", return_value="dummy-replacement-key"):
            self.assertEqual(play.main(["--set-api-key"]), 0)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), patch("opponents.getpass.getpass") as prompt:
            self.assertEqual(create_openrouter().api_key, "dummy-replacement-key")
            prompt.assert_not_called()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "dummy-env-override"}):
            self.assertEqual(create_openrouter().api_key, "dummy-env-override")
            self.assertEqual(self.key_file.read_text().strip(), "dummy-replacement-key")

    def test_menu_local_ai_back_invalid_and_quit(self):
        for answers, expected in [(["1"], "local"), (["2", "1"], "openrouter"),
                                  (["2", "0", "1"], "local"), (["bad", "2", "bad", "1"], "openrouter"),
                                  (["0"], None), (["2", "quit"], None)]:
            with self.subTest(answers=answers), patch("builtins.input", side_effect=answers):
                self.assertEqual(play.select_opponent(), expected)
        with patch("builtins.input", side_effect=EOFError):
            self.assertEqual(play.main([]), 0)

    def test_launcher_dispatches_keyboard_and_physical_board(self):
        with patch("play_stockfish.run", return_value=0) as run, patch("builtins.input", return_value="1"):
            self.assertEqual(play.main([]), 0)
            self.assertEqual(run.call_args.args[0].opponent, "local")
        with patch("board_game.run", return_value=0) as run, patch("builtins.input") as prompt:
            self.assertEqual(play.main(["--board", "--opponent", "openrouter", "--port", "test-port"]), 0)
            args = run.call_args.args[0]
            self.assertEqual((args.opponent, args.mode, args.port), ("openrouter", "pvc", "test-port"))
            prompt.assert_not_called()

    def test_cloud_game_retries_same_position_and_never_starts_stockfish(self):
        game = Game()
        replies = [error.URLError("offline")] * 3 + [response("e7e5")]
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), \
                patch("play_stockfish.Game", return_value=game), \
                patch("opponents.Stockfish", side_effect=AssertionError("AI Mode started Stockfish")), \
                patch("openrouter_engine.request.urlopen", side_effect=replies) as send, \
                patch("builtins.input", side_effect=["e2e4", "", "quit"]):
            self.assertEqual(play.main(["--opponent", "openrouter"]), 0)
        self.assertEqual(game.move_history, ["e2e4", "e7e5"])
        positions = [json.loads(call.args[0].data)["messages"][1]["content"] for call in send.call_args_list]
        self.assertEqual(len(positions), 4)
        self.assertTrue(all(position == positions[0] for position in positions))

    def test_interactive_ai_mode_prompts_for_key_without_export_or_echo(self):
        game = Game()
        output = io.StringIO()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), \
                patch("opponents.sys.stdin.isatty", return_value=True), \
                patch("opponents.getpass.getpass", return_value="dummy-hidden-key") as key_prompt, \
                patch("play_stockfish.Game", return_value=game), \
                patch("openrouter_engine.request.urlopen", return_value=response("e7e5")) as send, \
                patch("builtins.input", side_effect=["2", "1", "e2e4", "quit"]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(play.main([]), 0)
            self.assertEqual(os.environ["OPENROUTER_API_KEY"], "")
        key_prompt.assert_called_once()
        self.assertEqual(send.call_args.args[0].get_header("Authorization"), "Bearer dummy-hidden-key")
        self.assertNotIn("dummy-hidden-key", output.getvalue())
        self.assertEqual(game.move_history, ["e2e4", "e7e5"])

    def test_noninteractive_missing_key_does_not_prompt_or_send_requests(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), \
                patch("opponents.sys.stdin.isatty", return_value=False), \
                patch("opponents.getpass.getpass") as key_prompt, \
                patch("openrouter_engine.request.urlopen") as send:
            with self.assertRaisesRegex(OpenRouterError, "OPENROUTER_API_KEY"):
                play.main(["--opponent", "openrouter"])
        key_prompt.assert_not_called()
        send.assert_not_called()

    def test_cloud_can_play_white_and_quit_after_failure(self):
        game = Game()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), \
                patch("play_stockfish.Game", return_value=game), \
                patch("openrouter_engine.request.urlopen", return_value=response("e2e4")), \
                patch("builtins.input", return_value="quit"):
            self.assertEqual(play.main(["--opponent", "openrouter", "--computer", "white"]), 0)
        self.assertEqual(game.move_history, ["e2e4"])
        game = Game()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}), \
                patch("play_stockfish.Game", return_value=game), \
                patch("openrouter_engine.request.urlopen", side_effect=TimeoutError), \
                patch("builtins.input", side_effect=["e2e4", "quit"]):
            self.assertEqual(play.main(["--opponent", "openrouter"]), 0)
        self.assertEqual(game.move_history, ["e2e4"])

    def test_local_mode_uses_uci_engine_without_cloud_key_or_requests(self):
        game = Game()
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "fake-stockfish"
            binary.write_text("#!" + sys.executable + "\n" + FAKE)
            binary.chmod(0o755)
            with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), \
                    patch("play_stockfish.Game", return_value=game), \
                    patch("openrouter_engine.request.urlopen") as send, \
                    patch("builtins.input", side_effect=["e2e5", "e2e4", "quit"]):
                self.assertEqual(play.main(["--opponent", "local", "--engine", str(binary), "--movetime", "50"]), 0)
                send.assert_not_called()
        self.assertEqual(len(game.move_history), 2)
        self.assertEqual(game.move_history[0], "e2e4")

    def test_physical_ai_error_waits_for_retry_then_occupancy_confirmation(self):
        class Link:
            def __init__(self): self.commands = []
            def request(self, command): self.commands.append(command)
        with Game() as game:
            link = Link()
            opponent = OpenRouter("key", "model", attempts=1, report=lambda *_: None)
            board = PhysicalGame(game, link, lambda *_: None, engine=opponent)
            board.on_board(occupancy(fen_board(game.fen())))
            board.on_board(expected_occupancy(game.fen(), "e2e4"))
            self.assertTrue(board.try_move("e2e4"))
            before = game.fen()
            with patch("openrouter_engine.request.urlopen", side_effect=TimeoutError) as send:
                board.maybe_computer_turn()
                board.maybe_computer_turn()
                self.assertEqual(send.call_count, 1)
            self.assertTrue(board.opponent_failed)
            self.assertEqual(game.fen(), before)
            board.opponent_failed = False
            with patch("openrouter_engine.request.urlopen", return_value=response("e7e5")):
                board.maybe_computer_turn()
            self.assertEqual(game.fen(), before)
            self.assertEqual(board.computer_move, "e7e5")
            self.assertIn("MARK e7 e5 LEGAL", link.commands)
            self.assertFalse(any(command.startswith(("ARM", "MOVE", "GOTO")) for command in link.commands))
            board.on_board(expected_occupancy(before, "e7e5"))
            self.assertTrue(board.try_move("e7e5"))
            self.assertEqual(game.move_history, ["e2e4", "e7e5"])


if __name__ == "__main__":
    unittest.main()

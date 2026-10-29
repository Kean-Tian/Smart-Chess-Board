import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import coaching
import play
from board_game import PhysicalGame, expected_occupancy, fen_board, occupancy
from coaching import CoachingSession
from openrouter_engine import CoachingHint, OpenRouter, OpenRouterError, ask_coaching_hint
from scb_rules import Game
from stockfish_engine import START_FEN


class Coach:
    def __init__(self, fail_first=False):
        self.requests = []
        self.fail_first = fail_first

    def coach(self, game):
        self.requests.append(game.fen())
        if self.fail_first:
            self.fail_first = False
            raise OpenRouterError("Simulated connection failure")
        return CoachingHint(game.legal_moves()[0], "Control the center and prepare to develop your pieces.")

    def __enter__(self): return self
    def __exit__(self, *args): pass


def response(advice):
    content = advice if isinstance(advice, str) else json.dumps(advice, ensure_ascii=False)
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


class CoachingTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        self.redirect = contextlib.ExitStack()
        temporary = self.redirect.enter_context(tempfile.TemporaryDirectory())
        self.redirect.enter_context(patch("api_key_store.KEY_FILE", Path(temporary) / ".openrouter-key"))
        self.redirect.enter_context(contextlib.redirect_stdout(self.output))
        self.redirect.enter_context(contextlib.redirect_stderr(self.output))
        self.addCleanup(self.redirect.close)

    def test_all_four_settings_and_only_human_moves_are_played(self):
        for white, black in [(False, False), (False, True), (True, False), (True, True)]:
            game, coach = Game(), Coach()
            with self.subTest(white=white, black=black), \
                    patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), \
                    patch("coaching.Game", return_value=game), \
                    patch("coaching.create_openrouter", return_value=coach) as factory, \
                    patch("opponents.Stockfish", side_effect=AssertionError("Coaching started an opponent")), \
                    patch("builtins.input", side_effect=["e2e4", "e7e5", "quit"]):
                self.assertEqual(play.main(["--coaching", "--coach-white", "on" if white else "off",
                                           "--coach-black", "on" if black else "off"]), 0)
            self.assertEqual(game.move_history, ["e2e4", "e7e5"])
            self.assertEqual([fen.split()[1] for fen in coach.requests],
                             (["w"] if white else []) + (["b"] if black else []) + (["w"] if white else []))
            self.assertEqual(factory.call_count, int(white or black))

    def test_menu_prompts_for_each_side_and_both_off_needs_no_key(self):
        with patch("builtins.input", side_effect=["2", "2", "off", "off", "quit"]), \
                patch("coaching.create_openrouter", side_effect=AssertionError("Both OFF requested a key")):
            self.assertEqual(play.main([]), 0)
        self.assertIn("AI Coaching (two players)", self.output.getvalue())
        self.assertIn("White=OFF, Black=OFF", self.output.getvalue())
        with patch("builtins.input", side_effect=["bad", "enable", "disable"]):
            args = type("Args", (), {"coach_white": None, "coach_black": None})()
            self.assertEqual(coaching.configure_coaching(args), {"w": True, "b": False})
        with patch("builtins.input", side_effect=EOFError):
            self.assertEqual(play.main(["--coaching"]), 0)

    def test_runtime_settings_independent_and_illegal_moves_do_not_repeat_hints(self):
        game, coach = Game(), Coach()
        commands = ["coach black on", "e2e4", "coach black off", "hint", "e7e5",
                    "coach white on", "e2e5", "coach", "coach black on", "g1f3", "quit"]
        with patch("coaching.Game", return_value=game), \
                patch("coaching.create_openrouter", return_value=coach), \
                patch("builtins.input", side_effect=commands):
            self.assertEqual(play.main(["--coach-white", "off", "--coach-black", "off"]), 0)
        self.assertEqual(game.move_history, ["e2e4", "e7e5", "g1f3"])
        self.assertEqual([fen.split()[1] for fen in coach.requests], ["b", "w", "b"])
        self.assertIn("Black coaching is OFF", self.output.getvalue())

    def test_menu_key_prompt_and_cloud_hint_only_for_enabled_next_player(self):
        game = Game()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), \
                patch("opponents.sys.stdin.isatty", return_value=True), \
                patch("opponents.getpass.getpass", return_value="dummy-hidden-coach-key") as key_prompt, \
                patch("coaching.Game", return_value=game), \
                patch("openrouter_engine.request.urlopen",
                      return_value=response({"move": "e7e5", "hint": "Control the center and open lines for Black's pieces."})) as send, \
                patch("builtins.input", side_effect=["2", "2", "off", "on", "e2e4", "quit"]):
            self.assertEqual(play.main([]), 0)
        key_prompt.assert_called_once()
        send.assert_called_once()
        self.assertIn("AI Coaching [Black] > e7e5", self.output.getvalue())
        self.assertNotIn("AI Coaching [White]", self.output.getvalue())
        self.assertNotIn("dummy-hidden-coach-key", self.output.getvalue())
        self.assertEqual(game.move_history, ["e2e4"])

    def test_failed_hint_can_be_retried_without_blocking_human_play(self):
        game, coach = Game(), Coach(fail_first=True)
        with patch("coaching.Game", return_value=game), \
                patch("coaching.create_openrouter", return_value=coach), \
                patch("builtins.input", side_effect=["e2e5", "hint", "e2e4", "e7e5", "quit"]):
            self.assertEqual(play.main(["--coaching", "--coach-white", "on", "--coach-black", "off"]), 0)
        self.assertEqual(game.move_history, ["e2e4", "e7e5"])
        self.assertEqual(len(coach.requests), 3)
        self.assertEqual(coach.requests[0], coach.requests[1])
        self.assertIn("Both players can continue", self.output.getvalue())

    def test_hints_never_change_position_or_run_after_checkmate(self):
        with Game() as game:
            coach = Coach()
            with CoachingSession(game, {"w": True, "b": True}, lambda: coach, lambda *_: None) as session:
                before = game.fen()
                self.assertIsNotNone(session.show_hint())
                self.assertEqual(game.fen(), before)
                session.show_hint()
                self.assertEqual(len(coach.requests), 1)
                for move in ["f2f3", "e7e5", "g2g4", "d8h4"]:
                    self.assertTrue(game.play(move))
                self.assertIn("Checkmate", game.status())
                session.show_hint(force=True)
                self.assertEqual(len(coach.requests), 1)

    def test_openrouter_coaches_correct_side_with_legal_move_and_short_english_explanation(self):
        with Game() as game:
            provider = OpenRouter("dummy-key", "test/model", report=lambda *_: None)
            for move, side in [("e2e4", "White"), ("e7e5", "Black")]:
                before = game.fen()
                with patch("openrouter_engine.request.urlopen",
                           return_value=response({"move": move, "hint": "Control the center."})) as send:
                    advice = provider.coach(game)
                self.assertEqual(advice, CoachingHint(move, "Control the center."))
                self.assertEqual(game.fen(), before)
                payload = json.loads(send.call_args.args[0].data)
                self.assertIn(f"You coach {side}", payload["messages"][0]["content"])
                self.assertIn("one short English sentence, at most 20 words", payload["messages"][0]["content"])
                self.assertIn(before, payload["messages"][1]["content"])
                self.assertTrue(game.play(move))

        with patch("openrouter_engine.request.urlopen",
                   return_value=response({"move": "e2e4", "hint": " ".join(["word"] * 30)})):
            advice = ask_coaching_hint(START_FEN, ["e2e4"], "dummy-key", "test/model")
        self.assertLessEqual(len(advice.hint.split()), 20)

    def test_malformed_and_illegal_coaching_responses_are_rejected(self):
        for advice in ["not JSON", [], {"move": "e2e5", "hint": "Illegal move."},
                       {"move": "e2e4", "hint": None}, {"move": "e2e4", "hint": ""},
                       {"move": "e2e4", "hint": "x" * 1001}, {"move": "e2e4", "hint": "\x1b[2J"}]:
            with self.subTest(advice=advice), patch("openrouter_engine.request.urlopen", return_value=response(advice)):
                with self.assertRaises(OpenRouterError):
                    ask_coaching_hint(START_FEN, ["e2e4"], "dummy-key", "test/model")
        with Game() as game, patch("openrouter_engine.request.urlopen", side_effect=[
                response({"move": "e2e5", "hint": "Illegal move."}),
                response({"move": "e2e4", "hint": "Control the center."})]) as send:
            before = game.fen()
            self.assertEqual(OpenRouter("dummy-key", report=lambda *_: None).coach(game).move, "e2e4")
            self.assertEqual(send.call_count, 2)
            self.assertEqual(game.fen(), before)

    def test_physical_coaching_waits_for_confirmed_human_move(self):
        class Link:
            def __init__(self): self.commands = []
            def request(self, command): self.commands.append(command)
        with Game() as game:
            coach, link = Coach(), Link()
            with CoachingSession(game, {"w": False, "b": True}, lambda: coach, lambda *_: None) as session:
                manager = PhysicalGame(game, link, lambda *_: None, coaching=session)
                manager.on_board(occupancy(fen_board(game.fen())))
                self.assertFalse(manager.try_move("e2e4"))
                self.assertEqual(coach.requests, [])
                manager.on_board(expected_occupancy(game.fen(), "e2e4"))
                self.assertEqual(game.move_history, ["e2e4"])
                self.assertEqual(len(coach.requests), 1)
                manager.on_board(occupancy(fen_board(game.fen())))
                self.assertEqual(len(coach.requests), 1)
                manager.on_board(expected_occupancy(game.fen(), "e7e5"))
                self.assertTrue(manager.try_move("e7e5"))
                self.assertEqual(game.move_history, ["e2e4", "e7e5"])
                self.assertEqual(len(coach.requests), 1)
                self.assertFalse(any(command.startswith(("ARM", "MOVE", "GOTO")) for command in link.commands))


if __name__ == "__main__":
    unittest.main()

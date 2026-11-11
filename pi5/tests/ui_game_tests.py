"""Native rules + real SQLite tests, without serial hardware or network access."""
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from game_store import GameStore
from ui_game import GameSession, START_OCCUPANCY
from board_game import expected_occupancy, occupancy, fen_board


class Clock:
    def __init__(self): self.value = 100.0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = GameStore(Path(self.temp.name) / "players.sqlite3")
        self.store.db.execute("INSERT INTO players(name) VALUES('White test')")
        self.store.db.execute("INSERT INTO players(name) VALUES('Black test')")
        self.store.db.commit()
        self.clock = Clock()
        self.session = GameSession(self.store, now=self.clock)
        self.session.connection(True)

    def tearDown(self):
        self.session.close()
        self.store.close()
        self.temp.cleanup()

    def start(self, mode="pvp", minutes=5, human="w"):
        s = self.session
        s.prepare(mode, 1, 2, human, minutes)
        s.on_board(START_OCCUPANCY)
        self.assertTrue(s.check())
        s.start(True)

    def move(self, move):
        s = self.session
        s.on_board(expected_occupancy(s.game.fen(), move))
        s.event("MOVE " + move)

    def test_start_gate_requires_fresh_board_and_manual_confirmation(self):
        s = self.session
        s.prepare("pvp", 1, 2, "w", 5)
        with self.assertRaises(ValueError): s.start(True)
        s.on_board(0)
        self.assertFalse(s.check())
        s.on_board(START_OCCUPANCY)
        self.assertTrue(s.check())
        with self.assertRaises(ValueError): s.start(False)
        self.clock.advance(3)
        with self.assertRaises(ValueError): s.start(True)
        self.assertEqual(self.store.history()["total"], 0)

    def test_move_clocks_pause_resume_and_durable_review(self):
        self.start()
        s = self.session
        self.clock.advance(1.2)
        self.move("e2e4")
        self.assertEqual(s.game.move_history, ["e2e4"])
        self.assertEqual(s.clock_values(), (298800, 300000))
        self.clock.advance(0.5)
        s.tick_clock_only()
        s.pause()
        self.clock.advance(8)
        s.tick()
        self.assertEqual(s.clock_values(), (298800, 299500))
        s.on_board(occupancy(fen_board(s.game.fen())))
        s.resume()
        self.move("e7e5")
        game_id = s.game_id
        s.end("1/2-1/2")
        self.assertEqual(self.store.review(game_id, 0)["move"], "")
        self.assertEqual(self.store.review(game_id, 1)["move"], "e2e4")
        final = self.store.review(game_id, 500)
        self.assertEqual((final["ply"], final["move"], final["result"]), (2, "e7e5", "1/2-1/2"))
        self.assertEqual(s.game.move_history, ["e2e4", "e7e5"])
        other = GameStore(self.store.path)
        self.assertEqual(other.review(game_id, 1)["move"], "e2e4")
        other.close()

    def test_capture_not_committed_on_lift(self):
        self.start(minutes=0)
        self.move("e2e4")
        self.move("d7d5")
        s = self.session
        mask = occupancy(fen_board(s.game.fen()))
        s.on_board(mask & ~(1 << 28))
        s.event("LIFT e4")
        self.assertEqual(len(s.game.move_history), 2)
        s.on_board(mask & ~(1 << 28) & ~(1 << 35))
        s.event("LIFT d5")
        self.move("e4d5")
        self.assertEqual(s.game.move_history[-1], "e4d5")

    def test_castling_waits_for_rook_and_ignores_trailing_candidate(self):
        self.start(minutes=0)
        for move in ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]:
            self.move(move)
        s = self.session
        mask = occupancy(fen_board(s.game.fen()))
        s.on_board((mask & ~(1 << 4)) | (1 << 6))
        s.event("MOVE e1g1")
        self.assertEqual(s.pending, "e1g1")
        final = expected_occupancy(s.game.fen(), "e1g1")
        s.on_board(final)
        s.event("MOVE h1f1")
        self.assertEqual(s.game.move_history[-1], "e1g1")
        self.assertFalse(s.restore)

    def test_promotion_requires_explicit_piece(self):
        self.start(minutes=0)
        for move in ["a2a4", "h7h5", "a4a5", "h5h4", "a5a6", "h4h3", "a6b7", "h3g2"]:
            self.move(move)
        s = self.session
        s.on_board(expected_occupancy(s.game.fen(), "b7a8q"))
        s.event("MOVE b7a8")
        self.assertEqual(len(s.promotions), 4)
        self.assertEqual(len(s.game.move_history), 8)
        self.assertTrue(s.commit("b7a8q", explicit=True))
        self.assertEqual(s.game.move_history[-1], "b7a8q")

    def test_illegal_move_disconnect_and_expired_clock(self):
        self.start()
        s = self.session
        s.on_board((START_OCCUPANCY & ~(1 << 12)) | (1 << 36))
        s.event("MOVE e2e5")
        self.assertTrue(s.restore)
        self.assertEqual(s.game.move_history, [])
        s.on_board(START_OCCUPANCY)
        self.assertFalse(s.restore)
        s.connection(False)
        self.assertTrue(s.paused)
        with self.assertRaises(ValueError): s.resume()
        s.connection(True)
        s.on_board(START_OCCUPANCY)
        s.resume()
        self.clock.advance(301)
        s.tick()
        self.assertTrue(s.paused)
        self.assertEqual(s.clock_values()[0], 0)
        self.assertEqual(s.result, "*")

    def test_checkmate_and_player_deletion_keep_actual_history(self):
        self.start(minutes=0)
        for move in ["f2f3", "e7e5", "g2g4", "d8h4"]:
            self.move(move)
        s = self.session
        self.assertFalse(s.active)
        self.assertEqual(s.result, "0-1")
        self.store.db.execute("DELETE FROM players WHERE id=1")
        self.store.db.commit()
        saved = self.store.review(s.game_id, 4)
        self.assertEqual(saved["white"], "White test")
        self.assertEqual(saved["result"], "0-1")

    def test_database_failure_does_not_advance_position(self):
        self.start(minutes=0)
        s = self.session
        fen = s.game.fen()
        self.store.db.execute("CREATE TRIGGER refuse_move BEFORE INSERT ON game_moves BEGIN SELECT RAISE(FAIL,'disk test'); END")
        self.store.db.commit()
        with self.assertRaises(sqlite3.Error): self.move("e2e4")
        self.assertEqual(s.game.fen(), fen)
        self.assertTrue(s.paused)

    def test_stale_board_pauses_without_fabricating_state(self):
        self.start(minutes=0)
        self.clock.advance(3)
        self.session.tick()
        self.assertTrue(self.session.paused)
        self.assertFalse(self.session.state()["synced"])
        self.assertEqual(self.session.game.move_history, [])
        self.session.on_board(START_OCCUPANCY)
        self.session.resume()
        self.assertFalse(self.session.paused)

    def test_failed_coach_has_no_fake_hint_and_human_game_continues(self):
        def unavailable():
            raise RuntimeError("Engine not installed for this test")
        self.session.engine_factory = unavailable
        self.start(mode="coach", minutes=0)
        for _ in range(100):
            self.session.tick()
            if self.session.hint_error: break
            time.sleep(0.005)
        self.assertTrue(self.session.hint_error)
        self.assertEqual(self.session.hint, "")
        self.move("e2e4")
        self.assertEqual(self.session.game.move_history, ["e2e4"])

    def test_real_stockfish_opponent_and_local_coaching(self):
        s = self.session
        self.start(mode="pvc", minutes=0, human="b")
        for _ in range(200):
            s.on_board(START_OCCUPANCY)
            s.tick()
            if s.computer_move: break
            time.sleep(0.02)
        self.assertIn(s.computer_move, s.game.legal_moves())
        self.move(s.computer_move)
        self.assertEqual(len(s.game.move_history), 1)
        s.end()
        self.start(mode="coach", minutes=0)
        for _ in range(200):
            s.on_board(START_OCCUPANCY)
            s.tick()
            if s.hint: break
            time.sleep(0.02)
        self.assertTrue(s.hint.startswith("Stockfish recommends"))
        self.assertEqual(s.game.move_history, [])

if __name__ == "__main__": unittest.main()

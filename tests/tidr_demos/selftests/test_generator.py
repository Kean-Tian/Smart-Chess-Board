"""Actual rules/player-store/GameStore integration, with no hardware/UI/service launch."""
import argparse
import contextlib
import fcntl
import io
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.runtime import (Blocked, RUNS, bootstrap, create_run, database_snapshot,
                            game_record, load_run, read_jsonl)
from generate_test_game import LABEL, MOVES, generate
from demo_19_record_persistence import evaluate


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.run = create_run(RUNS / ("generator-selftest-" + uuid.uuid4().hex), "records")
        self.addCleanup(lambda: shutil.rmtree(self.run))
        self.run, self.manifest = load_run(self.run)
        bootstrap()
        from scb_rules import Game
        try:
            with Game():
                pass
        except OSError as exc:
            self.skipTest(f"Native rules unavailable: {exc}")

    def test_generator_refuses_service_owned_run_before_writing(self):
        with (self.run / "service.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(Blocked):
                generate(self.run, self.manifest)
        self.assertFalse((self.run / "players.sqlite3").exists())

    @unittest.skipUnless(shutil.which("cc"), "C compiler required for native profile API integration")
    def test_generate_twice_preserves_records_and_cannot_pass_physical_checkoff(self):
        from game_store import GameStore
        first = generate(self.run, self.manifest)
        before = database_snapshot(self.manifest["database"])
        second = generate(self.run, self.manifest)
        after = database_snapshot(self.manifest["database"])
        self.assertNotEqual(first, second)
        self.assertEqual(game_record(before, first), game_record(after, first))
        self.assertEqual(len(after["games"]), 2)
        store = GameStore(self.manifest["database"])
        try:
            self.assertEqual(store.history()["total"], 2)
            for game_id in (first, second):
                self.assertEqual([store.review(game_id, ply)["move"] for ply in range(1, 5)], list(MOVES))
                final = store.review(game_id, 4)
                self.assertEqual(final["status"], "completed")
                self.assertEqual(final["result"], "0-1")
                self.assertIn("Checkmate", final["reason"])
                self.assertIn(LABEL, final["reason"])
                row = game_record(after, game_id)["game"]
                self.assertEqual(store.player(row["white_player_id"])["name"], "TIDR Fixture White")
                self.assertEqual(store.player(row["black_player_id"])["name"], "TIDR Fixture Black")
        finally:
            store.close()
        provenance = read_jsonl(self.run / "generated_games.jsonl")
        self.assertEqual(len([p for p in provenance if p["kind"] == "verified"]), 2)
        self.assertTrue(all(p["physical_gameplay_verified"] is False for p in provenance))
        args = argparse.Namespace(failure_run=None, game_id=first, expected_moves=" ".join(MOVES),
                                  white="TIDR Fixture White", black="TIDR Fixture Black", result="0-1")
        with contextlib.redirect_stdout(io.StringIO()):
            code = evaluate(self.run, self.manifest, args)
        self.assertEqual(code, 2)
        report = json.loads(next(self.run.glob("result-19-*.json")).read_text())
        self.assertEqual(report["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()

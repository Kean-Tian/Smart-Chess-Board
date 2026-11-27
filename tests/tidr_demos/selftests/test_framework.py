"""Software validation only. No service, UI, serial port or physical hardware is launched."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import unittest
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.runtime import (Blocked, RUNS, bootstrap, create_run, database_snapshot,
                            events, game_record, load_run, read_jsonl)
from common.observe import Observer, session_state
from demo_19_record_persistence import evaluate, failure_fixture
import demo_33_game_log as replay


class RunCase(unittest.TestCase):
    def setUp(self):
        self.run = create_run(RUNS / ("selftest-" + uuid.uuid4().hex), "failure")
        self.run, self.manifest = load_run(self.run)
        self.addCleanup(lambda: shutil.rmtree(self.run) if self.run.exists() else None)


class IsolationTests(RunCase):

    def test_existing_run_cannot_be_initialized_again(self):
        with self.assertRaises(FileExistsError):
            create_run(self.run, "failure")

    def test_database_symlink_and_hardlink_are_refused(self):
        sentinel = self.run / "sentinel"
        sentinel.write_text("must remain unchanged")
        database = self.run / "players.sqlite3"
        database.symlink_to(sentinel)
        with self.assertRaises(Blocked):
            load_run(self.run)
        database.unlink()
        import os
        os.link(sentinel, database)
        with self.assertRaises(Blocked):
            load_run(self.run)
        self.assertEqual(sentinel.read_text(), "must remain unchanged")

    def test_partial_json_line_is_not_accepted_as_evidence(self):
        path = self.run / "partial.jsonl"
        path.write_text('{"complete":true}\n{"partial":')
        self.assertEqual(read_jsonl(path), [{"complete": True}])

    def test_corrupt_complete_evidence_is_rejected(self):
        path = self.run / "corrupt.jsonl"
        path.write_text('not json\n')
        with self.assertRaises(ValueError):
            read_jsonl(path)


class ProductionIntegrationTests(RunCase):
    """Real production rules/SQLite with synthetic board input: NOT hardware proof."""

    def setUp(self):
        super().setUp()
        bootstrap()
        from scb_rules import Game, LIBRARY
        if not LIBRARY.is_file():
            self.skipTest("Existing native rules library unavailable")
        try:
            with Game():
                pass
        except OSError as exc:
            self.skipTest(f"Native rules unavailable on this host: {exc}")
        from game_store import GameStore
        from ui_game import GameSession, START_OCCUPANCY
        self.store = GameStore(self.manifest["database"])
        # Profiles are isolated software fixtures; checkoff profiles must be created in native UI.
        with self.store.db:
            self.store.db.executemany("INSERT INTO players(name) VALUES(?)", [("White fixture",), ("Black fixture",)])
        self.session = GameSession(self.store)
        self.session.connection(True)
        self.session.prepare("pvp", 1, 2, "w", 0, False)
        self.session.on_board(START_OCCUPANCY)  # SYNTHETIC input; never a hardware result.
        self.session.check()
        self.session.start(True)

    def tearDown(self):
        if hasattr(self, "session"):
            self.session.close()
        if hasattr(self, "store"):
            self.store.close()

    def test_real_abort_rolls_back_both_updates_without_advancing_live_game(self):
        from board_game import expected_occupancy
        self.session.pause()
        observer = Observer(self.run, self.manifest)
        observer.install()
        try:
            observer.emit("state", state=session_state(self.session))
            with contextlib.redirect_stdout(io.StringIO()):
                failure_fixture(self.run, self.manifest, True)
            before = game_record(database_snapshot(self.manifest["database"]), self.session.game_id)
            self.session.resume()
            self.session.on_board(expected_occupancy(self.session.game.fen(), "e2e4"))
            old_fen = self.session.game.fen()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "TIDR19 isolated"):
                self.session.commit("e2e4")
            after = game_record(database_snapshot(self.manifest["database"]), self.session.game_id)
            self.assertEqual(before["moves"], after["moves"])
            self.assertEqual(before["game"]["current_fen"], after["game"]["current_fen"])
            self.assertEqual(self.session.game.fen(), old_fen)
            self.assertEqual(self.session.game.move_history, [])
            self.assertTrue(self.session.paused and self.session.restore)
        finally:
            observer.close()
        trace = events(self.run)
        self.assertFalse([e for e in trace if e["kind"] == "observer_error"])
        self.assertTrue(any(e["kind"] == "call" and e.get("operation") == "GameStore.move" for e in trace))
        with contextlib.redirect_stdout(io.StringIO()):
            failure_fixture(self.run, self.manifest, False)

    def test_software_completion_cannot_pass_hardware_checkoff(self):
        from board_game import expected_occupancy
        observer = Observer(self.run, self.manifest)
        observer.install()
        try:
            for move in ("f2f3", "e7e5", "g2g4", "d8h4"):
                self.session.on_board(expected_occupancy(self.session.game.fen(), move))
                self.assertTrue(self.session.commit(move))
        finally:
            observer.close()
        trace = events(self.run)
        self.assertFalse([e for e in trace if e["kind"] == "observer_error"])
        completions = [e for e in trace if e["kind"] == "return" and
                       e.get("operation") == "GameSession.commit" and not e["data"]["state"]["active"]]
        self.assertEqual(len(completions), 1)
        self.assertEqual(completions[0]["data"]["snapshot"]["games"][0]["result"], "0-1")
        args = argparse.Namespace(failure_run=None, game_id=1, expected_moves="f2f3 e7e5 g2g4 d8h4",
                                  white="White fixture", black="Black fixture", result="0-1")
        # Use records-purpose metadata only for evaluator validation; still no physical evidence exists.
        metadata = dict(self.manifest, purpose="records")
        with contextlib.redirect_stdout(io.StringIO()):
            code = evaluate(self.run, metadata, args)
        self.assertEqual(code, 2, "Software-only observations must be BLOCKED")
        report = json.loads(next(self.run.glob("result-19-*.json")).read_text())
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any(c["name"] == "final hardware evidence" and c["status"] == "BLOCKED"
                            for c in report["checks"]))

    def replay_fixture(self, movement=False):
        """Synthetic evaluator input, real store review; no serial/UI is opened."""
        from board_game import expected_occupancy
        from ui_game import START_OCCUPANCY
        self.session.on_board(expected_occupancy(self.session.game.fen(), "e2e4"))
        self.session.commit("e2e4")
        self.session.end("1/2-1/2")
        self.session.prepare("pvp", 1, 2, "w", 0, False)
        self.session.on_board(START_OCCUPANCY)
        self.session.check()
        self.session.start(True)
        self.session.pause()
        observer = Observer(self.run, self.manifest)
        observer.install()
        args = argparse.Namespace(action="begin", window="software-fixture", saved_game_id=1)
        try:
            observer.emit("state", state=session_state(self.session), synthetic=True)
            with contextlib.redirect_stdout(io.StringIO()):
                replay.marker(self.run, self.manifest, args)
            observer.emit("ui_reply", message=self.store.history(), synthetic=True)
            for ply in (0, 1, 0):
                observer.emit("ui_reply", message=self.store.review(1, ply), synthetic=True)
            observer.emit("serial_request", command="PING", synthetic=True)
            observer.emit("serial_reply", frame_kind="STATUS", payload="software fixture", synthetic=True)
            if movement:
                observer.emit("serial_request", command="MOVE e2 e4", synthetic=True)
            observer.emit("state", state=session_state(self.session), synthetic=True)
            args.action = "end"
            with contextlib.redirect_stdout(io.StringIO()):
                replay.marker(self.run, self.manifest, args)
        finally:
            observer.close()
        with contextlib.redirect_stdout(io.StringIO()):
            code = replay.evaluate(self.run, args)
        result = json.loads(next(self.run.glob("result-33-*.json")).read_text())
        return code, result

    def test_replay_without_physical_display_evidence_is_blocked(self):
        code, result = self.replay_fixture()
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any(c["name"] == "every replay response matches saved positions/moves"
                            and c["status"] == "PASS" for c in result["checks"]))

    def test_replay_movement_attempt_is_fail_even_when_other_evidence_is_missing(self):
        code, result = self.replay_fixture(movement=True)
        self.assertEqual(code, 1)
        self.assertTrue(any(c["name"] == "no movement commands attempted during replay"
                            and c["status"] == "FAIL" for c in result["checks"]))


if __name__ == "__main__":
    unittest.main()

"""SOFTWARE fixtures only: no UI, socket, service, serial device or hardware launch."""
import argparse
import contextlib
import copy
import io
from pathlib import Path
import shutil
import sys
import unittest
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.runtime import (Blocked, RUNS, Report, bootstrap, create_run, events,
                            load_run, read_jsonl)
from common.move_observe import MoveObserver, move_state
from common.move_demo import marker, paired
from generate_test_game import generate
import demo_20_ambiguous_confirmation as demo20
import demo_22_illegal_restore as demo22
import demo_23_legal_destinations as demo23


class SyntheticObserver(MoveObserver):
    def emit(self, kind, **data):
        super().emit(kind, synthetic=True, **data)


@unittest.skipUnless(shutil.which("cc"), "Existing C compiler needed for production profile fixture API")
class MoveValidationTests(unittest.TestCase):
    def setUp(self):
        bootstrap()
        from scb_rules import Game
        try:
            with Game():
                pass
        except OSError as exc:
            self.skipTest(f"Native rules unavailable: {exc}")
        self.run = create_run(RUNS / ("move-selftest-" + uuid.uuid4().hex), "records")
        self.addCleanup(lambda: shutil.rmtree(self.run))
        self.run, self.manifest = load_run(self.run)
        generate(self.run, self.manifest)
        from game_store import GameStore
        from ui_game import GameSession, START_OCCUPANCY
        from ui_service import UiCore
        self.store = GameStore(self.manifest["database"])
        self.session = GameSession(self.store)
        self.core = UiCore(self.store, session=self.session)
        self.addCleanup(self.store.close)
        self.addCleanup(self.core.close)
        self.session.connection(True)
        self.session.prepare("pvp", 1, 2, "w", 0, False)
        self.start_mask = START_OCCUPANCY
        self.session.on_board(self.start_mask)  # Explicitly synthetic board input.
        self.session.check()
        self.session.start(True)
        self.observer = SyntheticObserver(self.run, self.manifest)
        self.observer.install()
        self.addCleanup(self.observer.close)

    def mark(self, action, tidr, case):
        self.observer.emit("mv_state", version=1, state=move_state(self.session))
        args = argparse.Namespace(action=action, case=case, window=case)
        with contextlib.redirect_stdout(io.StringIO()):
            marker(self.run, self.manifest, args, tidr)

    def captured(self, case):
        marks = [m for m in read_jsonl(self.run / "move_windows.jsonl") if m["window"] == case]
        return marks[0], marks[1], events(self.run)

    def assert_no_observer_errors(self):
        self.assertFalse([e for e in events(self.run) if e["kind"] == "observer_error"])

    def ambiguous_case(self, case):
        self.mark("begin", 20, case)
        e2, d2 = 1 << 12, 1 << 11
        self.session.on_board(self.start_mask & ~e2 & ~d2)
        self.session.event("AMBIGUOUS MULTI_SQUARE")
        if case == "valid":
            mask, move = (self.start_mask & ~e2) | (1 << 28), "e2e4"
        elif case == "invalid":
            mask, move = (self.start_mask & ~e2) | (1 << 36), "e2e5"
        else:
            mask, move = self.start_mask & ~e2, "e2e4"
        self.session.on_board(mask)
        # A candidate EVENT while ambiguous must not call the rule validator.
        self.session.event("MOVE " + move)
        self.assertEqual(self.session.game.move_history, [])
        self.core.handle({"cmd": "commit", "move": move})  # Synthetic direct UI handler, not a touchscreen.
        self.mark("end", 20, case)
        report = Report(20)
        demo20.evaluate_case(report, *self.captured(case))
        self.assert_no_observer_errors()
        self.assertFalse([c for c in report.checks if c["status"] == "FAIL"], report.checks)
        self.assertTrue(any("before confirmation" in c["name"] and c["status"] == "PASS" for c in report.checks))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(report.finish(self.run), 2, "Synthetic calls must not pass physical checkoff")
        return report

    def test_20_valid_confirmation_commits_only_after_explicit_validation(self):
        self.ambiguous_case("valid")
        self.assertEqual(self.session.game.move_history, ["e2e4"])

    def test_20_evaluator_detects_candidate_query_before_confirmation(self):
        self.ambiguous_case("valid")
        begin, end, trace = copy.deepcopy(self.captured("valid"))
        _, ambiguity_return = next((c, r) for c, r in paired(trace, "GameSession.event")
                                   if c["data"]["payload"].startswith("AMBIGUOUS"))
        confirmation, _ = next((c, r) for c, r in paired(trace, "GameSession.commit")
                               if c["data"].get("explicit"))
        # Synthetic bad trace tests the evaluator; no production function is changed.
        trace.append({"kind": "mv_query", "operation": "Game.legal_moves", "phase": "call",
                      "monotonic_ns": (ambiguity_return["monotonic_ns"] + confirmation["monotonic_ns"]) // 2})
        report = Report(20)
        demo20.evaluate_case(report, begin, end, trace)
        self.assertTrue(any("before confirmation" in c["name"] and c["status"] == "FAIL" for c in report.checks))

    def test_20_illegal_confirmation_preserves_accepted_state(self):
        self.ambiguous_case("invalid")
        self.assertEqual(self.session.game.move_history, [])
        self.assertTrue(self.session.restore)

    def test_20_physically_mismatched_confirmation_does_not_commit(self):
        report = self.ambiguous_case("mismatch")
        self.assertEqual(self.session.game.move_history, [])
        self.assertTrue(any("occupancy check" in c["name"] and c["status"] == "PASS" for c in report.checks))

    def test_22_rejects_blocks_restores_then_accepts_one_move(self):
        from board_game import expected_occupancy
        self.mark("begin", 22, "illegal-restore")
        self.session.on_board((self.start_mask & ~(1 << 12)) | (1 << 36))
        self.session.event("MOVE e2e5")
        self.assertTrue(self.session.restore)
        self.session.on_board((self.session.mask & ~(1 << 11)) | (1 << 27))
        self.session.event("MOVE d2d4")
        self.assertEqual(self.session.game.move_history, [])
        self.session.on_board(self.start_mask)
        self.assertFalse(self.session.restore)
        self.session.on_board(expected_occupancy(self.session.game.fen(), "e2e4"))
        self.session.event("MOVE e2e4")
        self.mark("end", 22, "illegal-restore")
        begin, end, trace = self.captured("illegal-restore")
        report = Report(22)
        demo22.evaluate_case(report, begin, end, trace)
        self.assert_no_observer_errors()
        self.assertFalse([c for c in report.checks if c["status"] == "FAIL"], report.checks)
        self.assertTrue(any("exactly one legal" in c["name"] and c["status"] == "PASS" for c in report.checks))
        broken = copy.deepcopy(trace)
        for c, r in paired(broken, "GameSession.commit"):
            if c["data"]["move"] == "e2e5":
                r["data"]["state"]["fen"] = "invalid captured accepted state"
        bad = Report(22)
        demo22.evaluate_case(bad, begin, end, broken)
        self.assertTrue(any("unchanged" in c["name"] and c["status"] == "FAIL" for c in bad.checks))

    def test_23_correct_sets_include_empty_blocked_rook_and_no_unproven_timing_pass(self):
        self.session.set_guidance(True)
        for source, index in (("e2", 12), ("g1", 6), ("a1", 0)):
            with self.subTest(source=source):
                self.session.on_board(self.start_mask)
                self.mark("begin", 23, source)
                self.session.on_board(self.start_mask & ~(1 << index))
                self.session.event("LIFT " + source)
                self.mark("end", 23, source)
                report = Report(23)
                demo23.evaluate_case(report, *self.captured(source))
                self.assertFalse([c for c in report.checks if c["status"] == "FAIL"], report.checks)
                self.assertTrue(any("production guidance set correct" in c["name"] and
                                    c["status"] == "PASS" for c in report.checks))
                self.assertTrue(any("timing observable" in c["name"] and c["status"] == "BLOCKED"
                                    for c in report.checks))
        self.assert_no_observer_errors()

    def test_23_timing_math_and_incorrect_guidance_detection_are_conservative(self):
        self.session.set_guidance(True)
        self.mark("begin", 23, "e2")
        self.session.on_board(self.start_mask & ~(1 << 12))
        self.session.event("LIFT e2")
        self.mark("end", 23, "e2")
        begin, end, trace = copy.deepcopy(self.captured("e2"))
        # Numeric fixtures solely test evaluator bounds. They are NOT hardware timestamps.
        begin["bound_start_ns"] = 1_000_000_000
        call, ret = next((c, r) for c, r in paired(trace, "GameSession.event") if c["data"]["payload"] == "LIFT e2")
        call["data"]["received_ns"] = 1_005_000_000
        call["observed_ns"] = 1_010_000_000
        ret["observed_ns"] = 1_500_000_000
        for q in trace:
            if q["kind"] == "mv_query":
                q["observed_ns"] = 1_020_000_000
        report = Report(23)
        demo23.evaluate_case(report, begin, end, trace)
        self.assertTrue(any("response <=500" in c["name"] and c["status"] == "PASS" for c in report.checks))
        ret["observed_ns"] = 1_600_000_000
        report = Report(23)
        demo23.evaluate_case(report, begin, end, trace)
        self.assertTrue(any("response <=500" in c["name"] and c["status"] == "BLOCKED" for c in report.checks))
        for q in trace:
            if q["kind"] == "mv_query":
                q["observed_ns"] = 1_550_000_000
        ret["data"]["state"]["legal_destinations"] = ["e5"]
        report = Report(23)
        demo23.evaluate_case(report, begin, end, trace)
        self.assertTrue(any("response <=500" in c["name"] and c["status"] == "FAIL" for c in report.checks))
        self.assertTrue(any("production guidance set" in c["name"] and c["status"] == "FAIL" for c in report.checks))

    def test_marker_blocks_legacy_or_missing_observer_state(self):
        args = argparse.Namespace(action="begin", case="valid", window="missing")
        with self.assertRaises(Blocked):
            marker(self.run, self.manifest, args, 20)


if __name__ == "__main__":
    unittest.main()

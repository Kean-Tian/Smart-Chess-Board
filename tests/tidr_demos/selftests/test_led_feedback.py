"""SOFTWARE ONLY: original feedback selection/DB APIs, no LED or serial hardware."""
import contextlib
import copy
import io
from pathlib import Path
import shutil
import sys
import time
import unittest
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.runtime import (RUNS, Report, append, bootstrap, create_run, database_snapshot,
                            events, load_run)
from common.display_clock_demo import pairs
from common.led_observe import LedObserver
from common.led_demo import accepted_anchor, mapping_proof, optical
from generate_test_game import generate
import demo_37_guidance_leds as demo37
import demo_38_accepted_leds as demo38
import demo_39_rejected_leds as demo39


class SyntheticObserver(LedObserver):
    def emit(self, kind, **data):
        super().emit(kind, synthetic=True, **data)


class OpticalAnalysisTests(unittest.TestCase):
    def fixture(self, lit):
        return {"reviewer": "software-test", "method": "SYNTHETIC bounds, NOT physical evidence",
                "evidence_sha256": "unit-fixture", "synchronized": True, "timebase": "pi_monotonic_ns",
                "uncertainty_ns": 1_000_000, "observations": [
                    {"role": "accepted", "anchor_token": "test", "all_64_inspected": True,
                     "lit": lit, "frame_reference": "SYNTHETIC", "optical_lower_ns": 1_200_000_000,
                     "optical_upper_ns": 1_210_000_000}]}

    def test_full_array_color_check_rejects_extra_and_wrong_squares(self):
        for lit, expected in (({"e2": "blue", "e4": "green"}, "PASS"),
                              ({"e2": "blue", "e4": "green", "a1": "red"}, "FAIL"),
                              ({"e2": "red", "e4": "red"}, "FAIL")):
            report = Report(38)
            optical(report, [self.fixture(lit)], "test", "accepted", "test", {"e2": "blue", "e4": "green"})
            self.assertEqual(report.checks[0]["status"], expected)
        report = Report(37)
        optical(report, [self.fixture({})], "test", "accepted", "test", {})
        self.assertEqual(report.checks[0]["status"], "PASS")

    def test_optical_latency_bounds_and_missing_synchronization(self):
        doc = self.fixture({"e2": "blue", "e4": "green"})
        def status():
            report = Report(38)
            optical(report, [doc], "test", "accepted", "test", {"e2": "blue", "e4": "green"},
                    1_000_000_000, 1_005_000_000)
            return report.checks[-1]["status"]
        self.assertEqual(status(), "PASS")
        doc["observations"][0]["optical_lower_ns"] = 1_495_000_000
        doc["observations"][0]["optical_upper_ns"] = 1_505_000_000
        self.assertEqual(status(), "BLOCKED")
        doc["observations"][0]["optical_lower_ns"] = 1_600_000_000
        doc["observations"][0]["optical_upper_ns"] = 1_610_000_000
        self.assertEqual(status(), "FAIL")
        doc["synchronized"] = False
        self.assertEqual(status(), "BLOCKED")


@unittest.skipUnless(shutil.which("cc"), "Compiler required for existing native player fixture API")
class ProductionFeedbackTests(unittest.TestCase):
    def setUp(self):
        bootstrap()
        from scb_rules import Game
        try:
            with Game():
                pass
        except OSError as exc:
            self.skipTest(f"Native rules unavailable: {exc}")
        self.run = create_run(RUNS / ("led-selftest-" + uuid.uuid4().hex), "records")
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
        self.observer = SyntheticObserver(self.run, self.manifest)
        self.observer.install()
        self.addCleanup(self.observer.close)
        self.session.connection(True)  # Synthetic fixture state; no real serial connection.
        self.session.prepare("pvp", 1, 2, "w", 0, False)
        self.mask = START_OCCUPANCY
        self.session.on_board(self.mask)
        self.session.check()
        self.session.start(True)
        self.begin = {"window": "software", "session": self.observer.session_id,
                      "state": self.state(), "snapshot": database_snapshot(self.manifest["database"])}

    def state(self):
        from common.display_clock_observe import dc_state
        return dc_state(self.session)

    def feedback(self):
        self.core.feedback_update()  # With link=None, original implementation sends NO device commands.

    def move(self, move):
        from board_game import expected_occupancy
        self.session.on_board(expected_occupancy(self.session.game.fen(), move))
        self.session.event("MOVE " + move)
        self.feedback()

    def finish_case(self, tidr, evaluator):
        end = {"state": self.state(), "snapshot": database_snapshot(self.manifest["database"])}
        report = Report(tidr)
        evaluator(report, self.begin, end, events(self.run), [])
        self.assertFalse([c for c in report.checks if c["status"] == "FAIL"], report.checks)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(report.finish(self.run), 2, "Backend-only traces must remain BLOCKED")
        self.assertFalse([e for e in events(self.run) if e["kind"] == "observer_error"])
        return report, end

    def test_original_guidance_and_return_commands_include_empty_rook_set(self):
        self.session.set_guidance(True)
        for source, index, expected in (("e2", 12, ["e3", "e4"]), ("g1", 6, ["f3", "h3"]), ("a1", 0, [])):
            self.session.on_board(self.mask & ~(1 << index))
            self.session.event("LIFT " + source)  # Synthetic input is never physical proof.
            self.feedback()
            self.assertEqual(self.session.legal_destinations, expected)
            self.session.on_board(self.mask)
            self.feedback()
            self.assertEqual(self.session.feedback_command, "LED_CLEAR")
        self.session.on_board(self.mask & ~(1 << 12))
        self.session.event("LIFT e2")
        self.feedback()
        self.move("e2e4")
        self.finish_case(37, demo37.evaluate_case)
        self.assertFalse([e for e in events(self.run) if e["kind"] == "led_command"])

    def test_post_persistence_anchor_and_original_feedback_replacement(self):
        self.move("e2e4")
        self.assertEqual(self.session.feedback_command, "MARK e2 e4 LEGAL")
        self.move("e7e5")
        self.assertEqual(self.session.feedback_command, "MARK e7 e5 LEGAL")
        trace = events(self.run)
        report = Report(38)
        for c, r in pairs(trace, "GameSession.commit"):
            self.assertIsNotNone(accepted_anchor(report, trace, "test", c, r))
        self.assertTrue(all(c["status"] == "PASS" for c in report.checks))
        current = self.session.mask
        self.session.on_board((current & ~(1 << 6)) | (1 << 22))
        self.session.event("MOVE g1g3")
        self.feedback()
        self.assertEqual(self.session.feedback_command, "MARK g1 g3 ILLEGAL")
        self.session.on_board(current)
        self.feedback()
        self.core.handle({"cmd": "end", "result": "*"})
        self.feedback()
        self.session.prepare("pvp", 1, 2, "w", 0, False)
        self.feedback()
        self.finish_case(38, demo38.evaluate_case)

    def test_warning_holds_through_toggle_partial_restore_and_detects_premature_clear(self):
        self.session.on_board((self.mask & ~(1 << 12)) | (1 << 36))
        self.session.event("MOVE e2e5")
        self.feedback()
        self.core.handle({"cmd": "guidance", "enabled": False})
        self.feedback()
        self.session.on_board((self.session.mask & ~(1 << 11)) | (1 << 27))
        self.session.event("MOVE d2d4")
        self.session.on_board((self.mask & ~(1 << 11)) | (1 << 27))
        self.feedback()
        self.assertTrue(self.session.restore)
        self.assertEqual(self.session.feedback_command, "MARK e2 e5 ILLEGAL")
        self.session.on_board(self.mask)
        self.feedback()
        self.assertEqual(self.session.feedback_command, "LED_CLEAR")
        _, end = self.finish_case(39, demo39.evaluate_case)
        bad = copy.deepcopy(events(self.run))
        rejection = next(r for c, r in pairs(bad, "GameSession.commit") if c["data"]["move"] == "e2e5")
        bad.append({"kind": "led_command", "observed_ns": rejection["observed_ns"] + 1,
                    "command": "LED_CLEAR", "production_feedback_path": False})
        report = Report(39)
        demo39.evaluate_case(report, self.begin, end, bad, [])
        self.assertTrue(any("premature" in c["name"] and c["status"] == "FAIL" for c in report.checks))

    def test_acknowledgment_does_not_supply_physical_evidence_and_missing_mapping_blocks(self):
        from scb_link import parse_frame
        parse_frame("ACK 42 MARK")
        transport = [e for e in events(self.run) if e["kind"] == "led_transport"]
        self.assertEqual(transport[-1]["frame_kind"], "ACK")
        self.assertFalse(transport[-1]["optical_measurement"])
        report = Report(38)
        optical(report, [], "test", "accepted", "no-physical-frame", {"e2": "blue", "e4": "green"}, 1, 2)
        self.assertTrue(all(c["status"] == "BLOCKED" for c in report.checks))
        self.assertFalse(mapping_proof(self.run)[0])


if __name__ == "__main__":
    unittest.main()

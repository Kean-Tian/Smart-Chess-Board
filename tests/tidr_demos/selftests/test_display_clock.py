"""Software-only validation with real monotonic production clocks; no device/UI launch."""
import argparse
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import time
import unittest
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.runtime import RUNS, Blocked, Report, append, bootstrap, create_run, digest, events, load_run, read_jsonl
from common.display_clock_observe import DisplayClockObserver, dc_state
from common.display_clock_demo import duration_check, pairs
from generate_test_game import generate
import demo_27_display_updates as display
import demo_28_clocks as clock


class SyntheticObserver(DisplayClockObserver):
    def emit(self, kind, **data):
        super().emit(kind, synthetic=True, **data)


class IntervalTests(unittest.TestCase):
    def test_upper_bound_is_not_treated_as_exact_late_transition(self):
        report = Report(28)
        duration_check(report, "within", 0, 500_000_000, 500)
        duration_check(report, "inconclusive", 0, 501_000_000, 500)
        duration_check(report, "definitely late", 501_000_000, 502_000_000, 500)
        self.assertEqual([c["status"] for c in report.checks], ["PASS", "BLOCKED", "FAIL"])


@unittest.skipUnless(shutil.which("cc"), "Compiler required for existing native player fixture API")
class DisplayClockTests(unittest.TestCase):
    def setUp(self):
        bootstrap()
        from scb_rules import Game
        try:
            with Game():
                pass
        except OSError as exc:
            self.skipTest(f"Existing native rules unavailable: {exc}")
        self.run = create_run(RUNS / ("dc-selftest-" + uuid.uuid4().hex), "records")
        self.addCleanup(lambda: shutil.rmtree(self.run))
        self.run, self.manifest = load_run(self.run)
        generate(self.run, self.manifest)
        from game_store import GameStore
        from ui_game import GameSession, START_OCCUPANCY
        from ui_service import UiCore
        self.store = GameStore(self.manifest["database"])
        self.session = GameSession(self.store)  # Default real time.monotonic, never a fake clock.
        self.core = UiCore(self.store, session=self.session)
        self.addCleanup(self.store.close)
        self.addCleanup(self.core.close)
        self.observer = SyntheticObserver(self.run, self.manifest)
        self.observer.install()
        self.addCleanup(self.observer.close)
        self.session.connection(True)  # Explicit synthetic connection/input, not physical proof.
        self.session.prepare("pvp", 1, 2, "w", 5, False)
        self.mask = START_OCCUPANCY
        self.session.on_board(self.mask)
        self.session.check()

    def sample(self):
        self.observer.emit("dc_state", observed_ns=time.monotonic_ns(), state=dc_state(self.session),
                           payload=self.core.state())

    def start(self):
        self.session.start(True)
        self.sample()

    def move(self, uci):
        from board_game import expected_occupancy
        self.session.on_board(expected_occupancy(self.session.game.fen(), uci))
        self.session.event("MOVE " + uci)  # Clearly synthetic test input, not a serial report.
        self.sample()

    def tick(self):
        time.sleep(0.005)
        self.session.tick()
        self.sample()

    def assert_observer_complete(self):
        self.assertFalse([e for e in events(self.run) if e["kind"] == "observer_error"])

    def test_clock_workflow_uses_real_clock_and_software_disconnect_never_passes_hardware(self):
        begin = {"window": "software-clocks", "case": "clock-workflow", "session": self.observer.session_id}
        self.start()
        self.tick()
        self.move("e2e4")
        self.tick()
        self.core.handle({"cmd": "pause"})
        paused = list(self.session.clocks)
        self.tick()
        self.session.resume()
        self.assertEqual(self.session.clocks, paused)
        self.tick()
        self.session.connection(False)  # Synthetic API call: no actual USB disconnection claimed.
        disconnected = list(self.session.clocks)
        self.tick()
        self.session.connection(True)
        self.session.on_board(self.session.mask)
        self.session.resume()
        self.assertEqual(self.session.clocks, disconnected)
        self.tick()
        self.core.handle({"cmd": "end", "result": "*"})
        self.tick()
        trace = events(self.run)
        errors, decreases, holds = clock.audit_ticks(trace, self.session.game_id)
        self.assertEqual(errors, [])
        self.assertTrue(all(n > 0 for n in decreases))
        self.assertTrue(all(n > 0 for n in holds.values()))
        report = Report(28)
        clock.evaluate_case(report, self.run, begin, {}, trace)
        self.assertFalse([c for c in report.checks if c["status"] == "FAIL"], report.checks)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(report.finish(self.run), 2)
        self.assertTrue(any("physical link failure" in c["name"] and c["status"] == "BLOCKED" for c in report.checks))
        self.assert_observer_complete()

    def test_inactive_clock_change_and_reset_between_samples_are_detected(self):
        self.start()
        self.move("e2e4")
        self.tick()
        trace = copy.deepcopy(events(self.run))
        _, ret = pairs(trace, "GameSession.tick")[-1]
        ret["state"]["clocks"][0] -= 0.001  # Mutate test evidence only, not a production clock.
        self.assertTrue(clock.audit_ticks(trace, self.session.game_id)[0])
        trace = copy.deepcopy(events(self.run))
        trace[-1]["state"]["clocks"][0] += 1000
        self.assertTrue(clock.audit_ticks(trace, self.session.game_id)[0])

    def test_socket_or_backend_state_cannot_prove_visible_update(self):
        self.start()
        call, ret = pairs(events(self.run), "GameSession.start")[0]
        report = Report(27)
        display.visible(report, [], "software", call, ret, "players")
        self.assertEqual([c["status"] for c in report.checks], ["BLOCKED", "BLOCKED"])

    def test_visibility_import_requires_matching_hash_and_detects_document_changes(self):
        video = self.run / "evidence" / "software-fixture.mp4"
        video.write_bytes(b"SOFTWARE TEST FIXTURE ONLY - no physical video")
        append(self.run / "attachments.jsonl", {"kind": "hardware", "label": "software",
               "path": str(video.relative_to(self.run)), "sha256": digest(video), "synthetic": True})
        doc = {"version": 1, "window": "software", "session": self.observer.session_id,
               "reviewer": "software-test", "method": "synthetic, no synchronization or visibility proof",
               "video_sha256": "wrong", "synchronized": False, "observations": []}
        source = self.run / "input.json"
        source.write_text(json.dumps(doc))
        with contextlib.redirect_stdout(io.StringIO()):
            display.import_visibility(self.run, source)
        begin = {"window": "software", "session": self.observer.session_id}
        self.assertEqual(display.documents(self.run, begin), [])
        doc["video_sha256"] = digest(video)
        source.write_text(json.dumps(doc))
        with contextlib.redirect_stdout(io.StringIO()):
            display.import_visibility(self.run, source)
        self.assertEqual(len(display.documents(self.run, begin)), 1)
        entry = read_jsonl(self.run / "display_visibility.jsonl")[-1]
        (self.run / entry["path"]).write_text("altered software evidence")
        with self.assertRaises(Blocked):
            display.documents(self.run, begin)

    def test_visibility_bounds_correctness_and_unsynchronized_evidence(self):
        self.start()
        call, ret = copy.deepcopy(pairs(events(self.run), "GameSession.start")[0])
        call["observed_ns"], ret["observed_ns"] = 1_000_000_000, 1_001_000_000
        observation = {"backend_token": call["token"], "field": "turn", "correct": True,
                       "observed_text": "White to move", "visible_lower_ns": 1_400_000_000,
                       "visible_upper_ns": 1_410_000_000, "frame_reference": "SYNTHETIC unit fixture"}
        doc = {"window": "software", "reviewer": "software-test", "method": "synthetic bounds, not hardware",
               "video_sha256": "test-only", "measurement_kind": "physical_touchscreen", "synchronized": True,
               "timebase": "pi_monotonic_ns", "uncertainty_ns": 10_000_000, "observations": [observation]}
        def statuses():
            report = Report(27)
            display.visible(report, [doc], "software", call, ret, "turn")
            return [c["status"] for c in report.checks]
        self.assertEqual(statuses(), ["PASS", "PASS"])
        observation["visible_lower_ns"], observation["visible_upper_ns"] = 2_200_000_000, 2_210_000_000
        self.assertEqual(statuses(), ["PASS", "FAIL"])
        observation["visible_lower_ns"], observation["visible_upper_ns"] = 1_995_000_000, 2_005_000_000
        self.assertEqual(statuses(), ["PASS", "BLOCKED"])
        doc["synchronized"] = False
        self.assertEqual(statuses(), ["PASS", "BLOCKED"])
        observation["observed_text"] = "Black to move"
        self.assertEqual(statuses(), ["FAIL", "BLOCKED"])

    def test_original_rules_generate_check_checkmate_and_sticky_error(self):
        self.start()
        for uci in ("e2e4", "f7f6", "d1h5"):
            self.move(uci)
        self.assertEqual(self.session.game.status(), "Check.")
        report = Report(27)
        display.evaluate_case(report, self.run, {"window": "check", "case": "check", "session": self.observer.session_id},
                              {"state": dc_state(self.session)}, events(self.run))
        self.assertTrue(any("native rules identify" in c["name"] and c["status"] == "PASS" for c in report.checks))
        self.core.handle({"cmd": "end", "result": "*"})
        self.session.prepare("pvp", 1, 2, "w", 5, False)
        self.session.on_board(self.mask)
        self.session.check()
        self.start()
        for uci in ("f2f3", "e7e5", "g2g4", "d8h4"):
            self.move(uci)
        self.assertTrue(self.session.game.status().startswith("Checkmate"))
        self.session.prepare("pvp", 1, 2, "w", 5, False)
        self.session.on_board(self.mask)
        self.session.check()
        self.start()
        self.session.on_board((self.mask & ~(1 << 12)) | (1 << 36))
        self.session.event("MOVE e2e5")
        message = self.session.message
        self.core.handle({"cmd": "guidance", "enabled": False})
        self.tick()
        self.assertTrue(self.session.restore)
        self.assertEqual(self.session.message, message)
        self.session.on_board(self.mask)
        self.assertFalse(self.session.restore)
        self.assertNotIn("Illegal", self.session.message)
        self.assert_observer_complete()


if __name__ == "__main__":
    unittest.main()

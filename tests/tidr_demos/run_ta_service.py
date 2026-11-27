"""Operator-only unified observation, using the existing shared service launcher.

This module adds no game, clock, database transaction, LED or service-control
implementation. Existing legacy and extended observation formats are both kept.
Static review only in this consolidation phase; no service/test was run.
"""
import sys

sys.dont_write_bytecode = True
from common import observe
from common.led_observe import LedObserver
from common.runtime import cli
from run_demo_service import main as shared_launcher

# Keep an immutable reference before the demo launcher selects a subclass.
LegacyObserver = observe.Observer


class TAObserver(LedObserver):
    def observe(self, frame, event, arg, name):
        legacy = name in {"GameSession.commit", "GameSession.end"}
        # New observers use independent pending dictionaries for mv/dc records.
        # The original base pending dictionary still owns legacy call/return pairs.
        if legacy and event == "call":
            LegacyObserver.observe(self, frame, event, arg, name)
        super().observe(frame, event, arg, name)
        if legacy and event == "return":
            LegacyObserver.observe(self, frame, event, arg, name)


def main():
    original = observe.Observer
    try:
        observe.Observer = TAObserver  # Demo-only class selection, never production patching.
        return shared_launcher()
    finally:
        observe.Observer = original


if __name__ == "__main__":
    raise SystemExit(cli(main))

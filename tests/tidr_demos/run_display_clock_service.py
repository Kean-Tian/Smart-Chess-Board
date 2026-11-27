"""Manually select display/clock observations and reuse the unchanged demo launcher."""
import sys

sys.dont_write_bytecode = True
from common import observe
from common.display_clock_observe import DisplayClockObserver
from common.runtime import cli
from run_demo_service import main as shared_launcher


def main():
    original = observe.Observer
    try:
        observe.Observer = DisplayClockObserver  # Demo-only selection, never a production replacement.
        return shared_launcher()
    finally:
        observe.Observer = original


if __name__ == "__main__":
    raise SystemExit(cli(main))

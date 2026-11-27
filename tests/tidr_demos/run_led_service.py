"""Manually run the unchanged shared launcher with extra demo-only LED observations."""
import sys

sys.dont_write_bytecode = True
from common import observe
from common.led_observe import LedObserver
from common.runtime import cli
from run_demo_service import main as shared_launcher


def main():
    original = observe.Observer
    try:
        observe.Observer = LedObserver  # Only a demo class selection; production code is untouched.
        return shared_launcher()
    finally:
        observe.Observer = original


if __name__ == "__main__":
    raise SystemExit(cli(main))

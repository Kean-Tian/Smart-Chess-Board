"""Select extra demo observations, then use the unchanged shared demo launcher.

Only the DEMO module's observer class is temporarily selected in memory. No
production class/function, source file, event, clock or return value is replaced.
"""
import sys

sys.dont_write_bytecode = True
from common import observe
from common.move_observe import MoveObserver
from common.runtime import cli
from run_demo_service import main as shared_launcher


def main():
    original = observe.Observer
    try:
        observe.Observer = MoveObserver
        return shared_launcher()
    finally:
        observe.Observer = original


if __name__ == "__main__":
    raise SystemExit(cli(main))

"""Two human players, with independently optional OpenRouter coaching."""
from contextlib import ExitStack
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rules" / "python"))
from scb_rules import Game
from openrouter_engine import OpenRouterError
from opponents import create_openrouter

SIDES = {"w": "White", "b": "Black"}


def add_coaching_arguments(parser):
    parser.add_argument("--coaching", action="store_true", help="Two human players with optional AI hints")
    parser.add_argument("--coach-white", choices=["on", "off"], help="White's independent coaching setting")
    parser.add_argument("--coach-black", choices=["on", "off"], help="Black's independent coaching setting")


def configure_coaching(args):
    settings = {}
    for side, name in SIDES.items():
        setting = getattr(args, f"coach_{name.lower()}", None)
        while setting is None:
            try:
                answer = input(f"{name} AI coaching [on/off] > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
            if answer in {"q", "quit"}:
                return None
            if answer in {"on", "enable", "yes", "y", "1"}:
                setting = "on"
            elif answer in {"off", "disable", "no", "n", "0"}:
                setting = "off"
            else:
                print("Choose on or off (or quit).")
        settings[side] = setting == "on"
    return settings


class CoachingSession:
    def __init__(self, game, settings, coach_factory, report=print):
        self.game, self.report = game, report
        self.enabled = dict(settings)
        self.coach_factory = coach_factory
        self._coach = None
        self._resources = ExitStack()
        self._last_position = None

    def show_settings(self):
        self.report("AI Coaching: " + ", ".join(
            f"{name}={'ON' if self.enabled[side] else 'OFF'}" for side, name in SIDES.items()))

    def show_hint(self, force=False):
        fen = self.game.fen()
        side = fen.split()[1]
        if not self.enabled[side]:
            if force:
                self.report(f"{SIDES[side]} coaching is OFF. Use coach {SIDES[side].lower()} on to enable it.")
            return None
        status = self.game.status()
        if (status and status != "Check.") or (not force and self._last_position == fen):
            return None
        self._last_position = fen
        try:
            if self._coach is None:
                self._coach = self._resources.enter_context(self.coach_factory())
            advice = self._coach.coach(self.game)
            if advice is None:
                return None
            if advice.move not in self.game.legal_moves():
                raise OpenRouterError("AI coach suggested an illegal move.")
        except OpenRouterError as exc:
            self.report(f"AI Coaching unavailable: {exc}")
            self.report("Both players can continue. Enter hint to retry on an enabled turn.")
            return None
        self.report(f"AI Coaching [{SIDES[side]}] > {advice.move}: {advice.hint}")
        return advice

    def handle_command(self, line):
        parts = line.split()
        if parts == ["hint"]:
            self.show_hint(force=True)
            return True
        if parts == ["coach"]:
            self.show_settings()
            return True
        if parts and parts[0] == "coach":
            if len(parts) == 3 and parts[1] in {"white", "black"} and parts[2] in {"on", "off"}:
                side = parts[1][0]
                self.enabled[side] = parts[2] == "on"
                self.show_settings()
                if self.game.fen().split()[1] == side and self.enabled[side]:
                    self.show_hint(force=True)
            else:
                self.report("Use coach white on/off, coach black on/off, coach, or hint.")
            return True
        return False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self._resources.__exit__(*args)


def run(args):
    settings = configure_coaching(args)
    if settings is None:
        return 0
    with Game() as game, CoachingSession(game, settings, lambda: create_openrouter(args.model)) as coaching:
        print("AI Coaching: two human players. Hints are optional; enter your own move.")
        print("Commands: e2e4, coach white on/off, coach black on/off, coach, hint, quit.")
        coaching.show_settings()
        while True:
            print(game.board_text())
            status = game.status()
            if status:
                print(status)
                if status != "Check.":
                    return 0
            coaching.show_hint()
            side = game.fen().split()[1]
            try:
                line = input(f"{SIDES[side]} > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return 0
            if line in {"q", "quit"}:
                return 0
            if coaching.handle_command(line):
                continue
            if not game.play(line):
                print("Illegal move. Position unchanged.")

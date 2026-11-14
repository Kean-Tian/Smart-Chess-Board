"""Non-blocking square LED guidance using the existing ESP32 line protocol."""
import time

from software_limits import FEEDBACK_ACK_TIMEOUT_S

HINT_DELAY_S = 5.0
HINT_BLINK_HALF_PERIOD_S = 0.5


def add_led_hint_arguments(parser):
    parser.add_argument("--led-hints", choices=["staged", "both"], default="staged",
                        help="Square LEDs: source first, then blinking destination (default), or both steady")


class MoveGuidance:
    def __init__(self, link, mode="staged", clock=None):
        if mode not in {"staged", "both"}:
            raise ValueError("LED hint mode must be staged or both")
        self.link, self.mode = link, mode
        self._clock = clock or time.monotonic
        self.move = None

    def _send(self, command):
        self.link.request(command, timeout=FEEDBACK_ACK_TIMEOUT_S)

    def start(self, move, mask):
        self.move = move
        self._started_at = self._clock()
        self._destination_at = None
        self._target_on = False
        source_index = (int(move[1]) - 1) * 8 + ord(move[0]) - ord("a")
        self._source_bit = 1 << source_index
        self._source_seen = mask is not None and bool(mask & self._source_bit)
        if self.mode == "both":
            self._send(f"MARK {move[:2]} {move[2:4]} LEGAL")
        else:
            self._send("LED_CLEAR")
            self._send(f"LED {move[:2]} 0 0 20")

    def update(self, mask):
        if self.move is None or self.mode == "both":
            return
        now = self._clock()
        lifted = False
        if mask is not None:
            occupied = bool(mask & self._source_bit)
            lifted = self._source_seen and not occupied
            self._source_seen |= occupied
        if self._destination_at is None:
            if not lifted and now - self._started_at < HINT_DELAY_S:
                return
            self._destination_at = now
        # Derive phase from elapsed time; delayed polls never replay missed flashes.
        target_on = int((now - self._destination_at) / HINT_BLINK_HALF_PERIOD_S) % 2 == 0
        if target_on != self._target_on:
            self._send(f"LED {self.move[2:4]} 0 {20 if target_on else 0} 0")
            self._target_on = target_on

    def clear(self):
        if self.move is not None:
            self.move = None
            self._send("LED_CLEAR")

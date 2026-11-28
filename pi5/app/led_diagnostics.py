"""Diagnostic-only LED ownership and cooperative sequencing on the existing LED executor.

No serial connection, clock/game/store mutation, motor command or dedicated thread
is created here. The service loop alone changes state; a single worker may have
one bounded request in flight. Exit retains ownership until a final clear ACK.
"""
from collections import deque
import time

CHANNEL_LIMIT = 32  # Existing SCB_LED_CHANNEL_LIMIT; checked against firmware by tests.
COLORS = {"red": (32, 0, 0), "green": (0, 32, 0), "blue": (0, 0, 32),
          "white": (32, 32, 32), "off": (0, 0, 0)}
CODES = {rgb: name[0].upper() if name != "off" else "." for name, rgb in COLORS.items()}


def square_index(square):
    if not isinstance(square, str) or len(square) != 2 or square[0] not in "abcdefgh" or square[1] not in "12345678":
        raise ValueError("Choose a square a1-h8")
    return (int(square[1]) - 1) * 8 + ord(square[0]) - 97


def square_name(index):
    return chr(97 + index % 8) + str(index // 8 + 1)


class LedDiagnostics:
    def __init__(self, executor, now=time.monotonic):
        self.executor, self.now = executor, now
        self.owned = self.closing = self.running = self.paused = False
        self.mode, self.phase = "", "closed"
        self.message = "LED diagnostics inactive. Commanded states are not optical verification."
        self.pixels = ["?"] * 64
        self.known = self.clear_acknowledged = False
        self.future = None
        self.generation = 0
        self.queue = deque()
        self.link = self.blocked_link = None
        self.needs_clear = False
        self.clear_stage = "status"
        self.after_clear = "idle"
        self.auto_square = self.auto_color = 0
        self.due = 0
        self.pattern = self.color = "off"
        self.selected = "a1"
        self.started = self.ended = None
        self.transition_index = 0

    def _cancel(self):
        self.generation += 1
        self.queue.clear()
        if self.future is not None:
            self.future.cancel()  # Running requests finish before the final clear.
        self.running = self.paused = False

    def _clear(self, after="idle", closing=False):
        self._cancel()
        self.needs_clear, self.clear_stage, self.after_clear = True, "status", after
        self.blocked_link = None  # Explicit Stop/Back may retry a bounded clear; errors do not loop.
        self.closing = closing
        self.clear_acknowledged = False
        self.phase = "stopping" if closing else "clearing"
        self.ended = self.now()

    def enter(self, mode, link):
        if mode not in {"auto", "manual", "current"}:
            raise ValueError("Unknown LED diagnostic page")
        if self.owned:
            raise ValueError("Finish clearing the previous LED diagnostic first")
        if link is None:
            raise ValueError("Connect the board in Sensor Test first")
        self.owned, self.mode, self.link = True, mode, link
        self.blocked_link = None
        self._clear()
        self.message = "Checking idle outputs and clearing LEDs..."

    def start(self):
        if self.mode != "auto" or not self.owned or self.closing:
            raise ValueError("Open Automatic RGB Test first")
        self.auto_square = self.auto_color = 0
        self.pattern = "automatic RGB"
        self._clear("auto")
        self.message = "Starting all 64 squares: red, green, blue, off."

    def pause(self):
        if self.mode != "auto" or not self.running:
            raise ValueError("No automatic sequence is running")
        self.paused = True
        self.phase = "paused"
        self.message = "Paused; the last dispatched color may finish. No next color is queued."

    def resume(self):
        if not self.paused:
            raise ValueError("Automatic sequence is not paused")
        self.paused = False
        self.phase, self.due = "running", self.now() + .2

    def manual(self, square, color):
        if self.mode != "manual" or not self.owned or self.closing:
            raise ValueError("Open Manual LED Test first")
        index = square_index(square)
        if color not in COLORS:
            raise ValueError("Choose red, green, blue, white or off")
        self.selected, self.color = square, color
        # Coalesce unsent taps per square; keep at most 64 manual commands.
        self.queue = deque(t for t in self.queue if t[1] != index)
        self.queue.append(("manual", index, color))

    def load(self, pattern):
        if self.mode != "current" or not self.owned or self.closing:
            raise ValueError("Open Current Limit Test first")
        if pattern not in {"maximum", "red", "green", "blue", "white", "transition"}:
            raise ValueError("Unknown load pattern")
        self.pattern = pattern
        self.transition_index = 0
        self._clear("pattern")
        self.message = "Applying existing 32/255 limit; external current measurement required."

    def stop(self, exit_mode=False):
        if self.owned:
            self._clear(closing=exit_mode)
            self.message = "Finishing in-flight request, then clearing LEDs..."

    def lost(self):
        if not self.owned:
            return
        self._clear(closing=True)
        self.pixels, self.known = ["?"] * 64, False
        self.phase = "disconnected"
        self.blocked_link = self.link
        self.message = "Disconnected. Sequence stopped; LEDs unknown. Reconnect to acknowledge a clear."

    def _submit(self, command, tag, index=None, color=None):
        generation, link = self.generation, self.link
        def operation():
            if generation != self.generation:
                return None
            return link.request(command, timeout=.4)
        self.future = self.executor.submit(operation)
        self.pending = (generation, tag, index, color)

    def _pattern_tasks(self):
        color = ("red", "green", "blue", "white")[self.transition_index] if self.pattern == "transition" else \
                "white" if self.pattern == "maximum" else self.pattern
        self.queue = deque(("load", i, color) for i in range(64))
        self.color, self.phase = color, "applying"

    def update(self, link, normal_busy=False):
        if not self.owned:
            return
        if link is not self.link:
            if self.link is not None:
                self.lost()
            self.link = link
            if link is not None:
                self.blocked_link = None
                self.phase = "clearing"
        if link is None:
            if self.phase != "disconnected":
                self.lost()
            return
        if self.future is not None:
            if not self.future.done():
                return
            future, pending = self.future, self.pending
            self.future = None
            generation, tag, index, color = pending
            if generation != self.generation:
                return  # Stale completion never updates commanded state or restarts a sequence.
            try:
                frame = future.result()
                if frame is None:
                    return
                if tag == "status":
                    from ui_hardware import values
                    status = values(frame)
                    if any(status.get(k) != "0" for k in ("armed", "moving", "magnet")):
                        raise ValueError("Actuators must be safely idle for LED diagnostics")
                    if not self.closing and status.get("fault") != "NONE":
                        raise ValueError("Resolve the board fault in Sensor Test before LED diagnostics")
                    self.clear_stage = "clear"
                else:
                    if frame.kind != "ACK":
                        raise ValueError("LED command not acknowledged")
                    if tag == "clear":
                        self.pixels, self.known, self.clear_acknowledged = ["."] * 64, True, True
                        self.needs_clear = False
                        if self.closing:
                            self.owned, self.closing, self.phase = False, False, "closed"
                            self.message = "Clear acknowledged; normal LED ownership restored. Verify actual darkness."
                            return
                        self.phase, self.color = "idle", "off"
                        if self.after_clear == "idle":
                            self.pattern = "off"
                        if self.after_clear in {"auto", "pattern"}:
                            self.started, self.ended = self.now(), None
                        if self.after_clear == "auto":
                            self.running, self.phase, self.due = True, "running", self.now()
                        elif self.after_clear == "pattern":
                            self._pattern_tasks()
                    else:
                        self.pixels[index], self.clear_acknowledged = CODES[COLORS[color]], False
                        self.selected, self.color = square_name(index), color
                        if tag == "auto_color":
                            self.auto_color += 1
                            self.due = self.now() + .2
                        elif tag == "auto_off":
                            self.auto_square += 1
                            self.auto_color = 0
                            if self.auto_square == 64:
                                self.running, self.phase, self.ended = False, "completed", self.now()
                                self.message = "Sequence complete: commanded 64 RGB tests. Visual verification required; no automatic PASS."
                        elif tag == "load" and not self.queue:
                            self.phase, self.due = "holding", self.now() + 1.0
            except Exception as exc:
                self._cancel()
                self.needs_clear = True
                self.known, self.clear_acknowledged = False, False
                self.pixels, self.blocked_link, self.phase = ["?"] * 64, link, "error"
                self.message = f"LED communication/safety error: {exc}. Stop/Back or reconnect; clear is unverified."
                return
        if normal_busy or self.blocked_link is link:
            return
        if self.needs_clear:
            self._submit("STATUS" if self.clear_stage == "status" else "LED_CLEAR", self.clear_stage)
            return
        if self.queue:
            tag, index, color = self.queue.popleft()
            rgb = COLORS[color]
            self._submit(f"LED {square_name(index)} {rgb[0]} {rgb[1]} {rgb[2]}", tag, index, color)
        elif self.running and not self.paused and self.now() >= self.due:
            index = self.auto_square
            color = ("red", "green", "blue")[self.auto_color] if self.auto_color < 3 else "off"
            rgb = COLORS[color]
            self._submit(f"LED {square_name(index)} {rgb[0]} {rgb[1]} {rgb[2]}",
                         "auto_color" if self.auto_color < 3 else "auto_off", index, color)
        elif self.pattern == "transition" and self.phase == "holding" and self.now() >= self.due:
            self.transition_index = (self.transition_index + 1) % 4
            self._pattern_tasks()

    def state(self):
        elapsed = 0 if self.started is None else max(0, (self.ended if self.ended is not None else self.now()) - self.started)
        return {"owned": self.owned, "mode": self.mode, "phase": self.phase, "running": self.running,
                "paused": self.paused, "closing": self.closing, "pixels": "".join(self.pixels),
                "square": self.selected, "color": self.color, "pattern": self.pattern,
                "progress": self.auto_square, "active_leds": sum(p not in {".", "?"} for p in self.pixels),
                "known": self.known, "clear_acknowledged": self.clear_acknowledged,
                "channel_limit": CHANNEL_LIMIT, "rgb": list(COLORS.get(self.color, COLORS["off"])),
                "elapsed_ms": round(elapsed * 1000), "current_limit_a": 2.0,
                "measured_current_a": None, "optical_verified": False, "message": self.message}

    def close(self, link):
        if not self.owned:
            return
        self._cancel()
        if self.future is not None:
            try:
                self.future.result()  # Original request has bounded serial timeouts; drain before final clear.
            except Exception:
                pass
            self.future = None
        if link is not None:
            try:
                frame = link.request("LED_CLEAR", timeout=.6)
                self.clear_acknowledged = frame.kind == "ACK"
            except Exception:
                self.clear_acknowledged = False
        else:
            self.clear_acknowledged = False
        self.owned = False
        self.message = "Shutdown clear acknowledged; verify actual darkness." if self.clear_acknowledged else \
                       "Shutdown clear unacknowledged: physically verify LED power/output safety."

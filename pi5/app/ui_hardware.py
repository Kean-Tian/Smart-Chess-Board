"""Bounded hardware operations; game state is mutated only on the UI service thread."""
import re


def values(frame):
    return dict(token.split("=", 1) for token in frame.payload.split() if "=" in token)


def stopped_status(link, *, calibrated=False):
    state = values(link.request("STATUS", timeout=0.6))
    if state.get("fault") != "NONE":
        raise ValueError("MCU fault is active or firmware lacks fault-status support")
    if any(state.get(key) != "0" for key in ("armed", "moving", "magnet")):
        raise ValueError("Actuators are not safely idle")
    if calibrated and (state.get("origin") != "1" or not state.get("steps", "").isdigit() or int(state["steps"]) <= 0):
        raise ValueError("Calibrate the carriage reference and steps before automatic motion")
    return state


def fresh_snapshot(link):
    # The MCU waits for new stable frames AFTER this request, rather than
    # returning an old BOARD event buffered before motion finished.
    frame = link.request("SNAPSHOT", timeout=0.8)
    state = values(frame)
    if (frame.kind != "SNAPSHOT" or state.get("fault") != "NONE" or
            not re.fullmatch(r"[0-9a-fA-F]{16}", state.get("occupy", "")) or
            not state.get("frame", "").isdigit()):
        raise ValueError("Invalid fresh MCU snapshot; update the MCU firmware")
    return int(state["occupy"], 16), frame.received_at


def reset_fault(link):
    link.request("CLEAR_FAULT", timeout=0.6)
    stopped_status(link)
    mask = fresh_snapshot(link)
    stopped_status(link)
    return mask


def execute_motion(link, move, cancelled):
    """A request is issued only by explicit UI action with runtime opt-in."""
    def check():
        if cancelled.is_set():
            raise ValueError("Motion cancelled; restore the accepted board position")
    success = False
    try:
        check()
        stopped_status(link, calibrated=True)
        link.request("LED_CLEAR", timeout=0.4)
        check()
        link.request("ARM", timeout=0.6)
        check()
        if link.request(f"GOTO {move[:2]}", timeout=30, wait_done=True).kind != "DONE":
            raise ValueError("Approach motion did not report completion")
        check()
        if link.request(f"MOVE {move[:2]} {move[2:4]}", timeout=30, wait_done=True).kind != "DONE":
            raise ValueError("Piece motion did not report completion")
        check()
        link.request("IDLE", timeout=0.6)
        stopped_status(link)
        mask = fresh_snapshot(link)
        stopped_status(link)
        check()
        success = True
        return mask
    finally:
        if not success:
            try:
                link.request("STOP", timeout=0.6)
            except Exception:
                pass

"""Software-only LED diagnostics tests: emulated MCU, real rules and temp SQLite.

No physical serial device, UI service, motor or network is opened by this suite.
"""
from concurrent.futures import Future
from pathlib import Path
import queue
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from led_diagnostics import LedDiagnostics, COLORS, CHANNEL_LIMIT, square_index, square_name
from scb_link import Frame
from game_store import GameStore
from ui_service import UiCore


class ImmediateExecutor:
    def submit(self, fn):
        f = Future()
        try: f.set_result(fn())
        except Exception as exc: f.set_exception(exc)
        return f


class DeferredExecutor:
    def __init__(self): self.jobs = []
    def submit(self, fn):
        f = Future()
        self.jobs.append((f, fn))
        return f
    def finish(self):
        f, fn = self.jobs.pop(0)
        if not f.cancelled():
            try: f.set_result(fn())
            except Exception as exc: f.set_exception(exc)


class Link:
    _failure = None
    def __init__(self):
        self.commands, self.pixels, self.events = [], [None]*64, queue.Queue()
        self.fail = False
        self.status = 'armed=0 moving=0 magnet=0 fault=NONE'
    def request(self, cmd, **kwargs):
        self.commands.append(cmd)
        if self.fail: raise TimeoutError('test disconnection')
        if cmd == 'STATUS': return Frame('STATUS', 1, self.status)
        if cmd == 'LED_CLEAR': self.pixels = [None]*64
        if cmd.startswith('LED '):
            _, square, r, g, b = cmd.split()
            self.pixels[square_index(square)] = tuple(map(int, (r,g,b)))
        return Frame('ACK', 1, cmd)
    def close(self): pass


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.t = 0.
        self.link = Link()
        self.d = LedDiagnostics(ImmediateExecutor(), lambda: self.t)
    def pump(self, n=8, step=.21):
        for _ in range(n):
            self.d.update(self.link)
            self.t += step
    def enter(self, mode):
        self.d.enter(mode, self.link)
        self.pump()
        self.assertTrue(self.d.known)
    def test_mapping_and_firmware_cap(self):
        for i in range(64): self.assertEqual(square_index(square_name(i)), i)
        self.assertEqual([square_index(s) for s in ('a1','h1','a8','h8')], [0,7,56,63])
        for s in ('a0','h9','A1','a11',None):
            with self.assertRaises(ValueError): square_index(s)
        header = Path(__file__).resolve().parents[2] / 'esp32/main/board_pins.h'
        import re
        self.assertRegex(header.read_text(), rf'SCB_LED_CHANNEL_LIMIT\s+{CHANNEL_LIMIT}U?\b')
        self.assertTrue(all(0 <= v <= CHANNEL_LIMIT for rgb in COLORS.values() for v in rgb))
    def test_all_64_rgb_sequence_and_only_one_led(self):
        self.enter('auto')
        self.d.start()
        for _ in range(1500):
            self.pump(1)
            self.assertLessEqual(sum(bool(p and any(p)) for p in self.link.pixels), 1)
            if self.d.phase == 'completed': break
        self.assertEqual(self.d.auto_square, 64)
        commands = [c for c in self.link.commands if c.startswith('LED ')]
        expected = [f'LED {square_name(i)} {r} {g} {b}' for i in range(64)
                    for r,g,b in (COLORS[c] for c in ('red','green','blue','off'))]
        self.assertEqual(commands, expected)
        self.assertFalse(self.d.state()['optical_verified'])
    def test_pause_resume_stop_restart(self):
        self.enter('auto'); self.d.start(); self.pump(12)
        self.d.pause(); self.pump(2)
        n = len(self.link.commands); self.pump(10)
        self.assertEqual(len(self.link.commands), n)
        self.d.resume(); self.pump(6)
        self.assertGreater(len(self.link.commands), n)
        self.d.start(); self.pump(5)
        self.assertEqual(self.d.auto_square, 0)
        self.d.stop(); self.pump()
        self.assertEqual(self.d.phase, 'idle')
        self.assertTrue(self.d.clear_acknowledged)
        n=len(self.link.commands); self.pump(20)
        self.assertEqual(len(self.link.commands), n)
    def test_manual_independence_coalescing_and_exit(self):
        self.enter('manual')
        for s,c in [('a1','red'),('e4','green'),('h8','blue')]: self.d.manual(s,c)
        self.pump()
        self.d.manual('e4','off'); self.pump()
        self.assertEqual([self.d.pixels[i] for i in (0,28,63)], ['R','.','B'])
        for _ in range(300): self.d.manual('b2','white')
        self.assertEqual(len(self.d.queue), 1)
        self.d.stop(exit_mode=True); self.pump()
        self.assertFalse(self.d.owned)
        self.assertEqual(self.link.commands[-1], 'LED_CLEAR')
        self.assertFalse(any(p and any(p) for p in self.link.pixels))
    def test_current_patterns_and_transitions(self):
        self.enter('current')
        for pattern in ('maximum','red','green','blue','white','transition'):
            self.d.load(pattern); self.pump(72, .001)
            self.assertEqual(self.d.phase, 'holding')
            self.assertEqual(self.d.state()['active_leds'], 64)
            self.assertIsNone(self.d.state()['measured_current_a'])
        self.pump(300, .02)
        self.assertGreater(self.d.transition_index, 0)
        for command in self.link.commands:
            if command.startswith('LED '):
                self.assertTrue(all(0 <= int(v) <= 32 for v in command.split()[2:]))
        self.d.stop(); self.pump(); n=len(self.link.commands); self.pump(100)
        self.assertEqual(n, len(self.link.commands))
    def test_safety_status_prevents_output(self):
        for status in ('armed=1 moving=0 magnet=0 fault=NONE', 'armed=0 moving=0 magnet=1 fault=NONE',
                       'armed=0 moving=0 magnet=0 fault=OVERCURRENT', 'moving=0 magnet=0'):
            self.d = LedDiagnostics(ImmediateExecutor(), lambda:self.t)
            self.link.status=status; self.link.commands=[]
            self.d.enter('current', self.link); self.pump()
            self.assertEqual(self.d.phase, 'error')
            self.assertFalse(any(c.startswith('LED') for c in self.link.commands))
    def test_error_no_false_clear_or_retry_loop_reconnect_clears_only(self):
        self.enter('auto'); self.d.start(); self.pump(8)
        self.link.fail=True; self.pump()
        self.assertEqual(self.d.phase, 'error'); self.assertFalse(self.d.known)
        n=len(self.link.commands); self.pump()
        self.assertEqual(n,len(self.link.commands))
        self.d.update(None)
        self.assertEqual(self.d.phase,'disconnected')
        replacement=Link(); self.link=replacement; self.pump()
        self.assertFalse(self.d.owned)
        self.assertEqual(replacement.commands, ['STATUS','LED_CLEAR'])
    def test_pending_cancelled_and_inflight_drained_before_exit(self):
        executor = DeferredExecutor()
        self.d=LedDiagnostics(executor, lambda:self.t)
        self.d.enter('auto',self.link); self.d.update(self.link)
        self.d.stop(exit_mode=True)
        executor.finish()  # cancelled STATUS is never sent
        self.assertEqual(self.link.commands, [])
        for _ in range(8):
            self.d.update(self.link)
            if executor.jobs: executor.finish()
        self.assertFalse(self.d.owned)
        self.d=LedDiagnostics(executor, lambda:self.t)
        self.d.enter('manual',self.link)
        for _ in range(5):
            self.d.update(self.link)
            if executor.jobs: executor.finish()
        self.d.manual('a1','red'); self.d.update(self.link)
        f,fn=executor.jobs.pop(0); f.set_running_or_notify_cancel()
        reply=fn()  # The already-running request reached the MCU before Stop.
        self.assertEqual(self.link.commands[-1], "LED a1 32 0 0")
        self.d.stop(exit_mode=True)
        self.assertTrue(self.d.owned)
        f.set_result(reply) # Its stale completion cannot update state or restart the sequence.
        for _ in range(8):
            self.d.update(self.link)
            if executor.jobs: executor.finish()
        self.assertFalse(self.d.owned)
        self.assertEqual(self.link.commands[-1], 'LED_CLEAR')
    def test_normal_request_drains_first_and_shutdown_clear(self):
        self.d.enter('manual', self.link)
        for _ in range(4): self.d.update(self.link, normal_busy=True)
        self.assertEqual(self.link.commands, [])
        self.pump(); self.d.manual('a1','white'); self.pump()
        self.d.close(self.link)
        self.assertFalse(self.d.owned)
        self.assertTrue(self.d.clear_acknowledged)
        self.assertEqual(self.link.commands[-1], 'LED_CLEAR')
    def test_invalid_inputs_never_emit(self):
        self.enter('manual'); n=len(self.link.commands)
        for s,c in [('i1','red'),('a1','255'),('a1',None)]:
            with self.assertRaises(ValueError): self.d.manual(s,c)
        self.pump(); self.assertEqual(len(self.link.commands), n)


class CoreIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=GameStore(Path(self.tmp.name)/'test.sqlite3')
        self.core=UiCore(self.store)
        self.core.link=Link()
    def tearDown(self):
        self.core.close(); self.store.close(); self.tmp.cleanup()
    def test_gameplay_blocks_diagnostic_and_diagnostic_blocks_gameplay(self):
        for key in ('active','paused'):
            setattr(self.core.session,key,True)
            with self.assertRaises(ValueError): self.core.handle({'cmd':'led_diag_enter','mode':'manual'})
            setattr(self.core.session,key,False)
        self.core.handle({'cmd':'led_diag_enter','mode':'manual'})
        for cmd in ('prepare','start','resume','execute_computer','commit','confirm_computer'):
            with self.assertRaises(ValueError): self.core.handle({'cmd':cmd})
    def test_no_clock_state_or_database_writes_and_exclusive_feedback(self):
        c=self.core; s=c.session
        before=self.store.db.iterdump(); before='\n'.join(before)
        state=(s.game,s.game_id,s.active,s.paused)
        c.handle({'cmd':'led_diag_enter','mode':'manual'})
        c.handle({'cmd':'led_diag_manual','square':'e4','color':'green'})
        c.session.tick_clock_only=lambda: self.fail('Diagnostic command ticked the game clock')
        c.handle({'cmd':'led_diag_clear'})
        c.feedback_update()
        self.assertIsNone(c.led_job)
        self.assertEqual(state,(s.game,s.game_id,s.active,s.paused))
        self.assertEqual(before,'\n'.join(self.store.db.iterdump()))
    def test_shutdown_drains_preexisting_normal_feedback_before_final_clear(self):
        import threading
        c=self.core
        entered, release=threading.Event(), threading.Event()
        request=c.link.request
        def delayed(cmd, **kwargs):
            if cmd.startswith('LED a1 '):
                entered.set()
                if not release.wait(2): raise TimeoutError('test timeout')
            return request(cmd, **kwargs)
        c.link.request=delayed
        c.session.feedback_command='LED a1 32 0 0'
        c.feedback_update()
        self.assertTrue(entered.wait(1))
        c.handle({'cmd':'led_diag_enter','mode':'manual'})
        timer=threading.Timer(.02, release.set)
        timer.start()
        try: c.close()
        finally: release.set(); timer.join()
        self.assertEqual(c.link.commands, ['LED a1 32 0 0','LED_CLEAR'])
        self.assertFalse(any(p and any(p) for p in c.link.pixels))

    def test_ui_loss_cancels_and_restores_feedback_after_clear(self):
        c=self.core; c.handle({'cmd':'led_diag_enter','mode':'manual'})
        c.controller_lost()
        import time
        deadline=time.monotonic()+2
        while c.led_diagnostics.owned and time.monotonic()<deadline:
            c.led_diagnostics.update(c.link); time.sleep(.001)
        self.assertFalse(c.led_diagnostics.owned)
        c.feedback_update()
        self.assertIsNotNone(c.led_job)
        c.led_job.result()
        self.assertEqual(c.link.commands[-1], 'LED_CLEAR')
        self.assertTrue(all(cmd=='STATUS' or cmd.startswith('LED') for cmd in c.link.commands))


if __name__ == '__main__': unittest.main()

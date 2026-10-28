"""Run local software checks without Pi, ESP32, serial ports, or network."""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pi5" / "app"))
sys.path.insert(0, str(ROOT / "pi5" / "rules" / "python"))
from stockfish_engine import Stockfish, self_test
from scb_rules import Game


def main():
    print("电脑软件自检：不连接 Pi / ESP32，不访问串口或网络。", flush=True)
    native_env = os.environ.copy()
    native_env["DYLD_LIBRARY_PATH"] = str(ROOT / "tools" / "mac_test" / "binaries")
    for binary in ["libchess_adapter_tests", "esp32_core_tests"]:
        subprocess.run([str(ROOT / "tools" / "mac_test" / "binaries" / binary)], check=True, env=native_env)
    for test in ["scb_link_tests.py", "board_game_tests.py",
                 "stockfish_engine_tests.py", "stockfish_board_tests.py"]:
        subprocess.run([sys.executable, str(ROOT / "pi5" / "tests" / test)], check=True)
    result = self_test()
    moves = []
    with Game() as game, Stockfish() as engine:
        for _ in range(12):
            status = game.status()
            if status and status != "Check.":
                break
            legal = game.legal_moves()
            move = engine.choose(game, 50)
            if move not in legal or not game.play(move):
                raise RuntimeError("真实引擎返回的走法未通过规则检查")
            moves.append(move)
        result.update({"rules_integration": "passed", "plies": len(moves), "moves": moves,
                       "final_fen": game.fen(), "test_suites_passed": 6,
                       "test_platform": platform.platform(),
                       "pi_or_esp32_hardware_tested": False})
    report = ROOT / "tools" / "mac_test" / "latest_result.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\nPASS：六组测试及真实 Stockfish 对弈验证通过。", flush=True)
    print("接下来可以输入 e2e4 测试人机对弈，输入 quit 退出。", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

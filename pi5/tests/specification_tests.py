import argparse
import importlib.util
import contextlib
import hashlib
import io
import json
import shutil
import struct
import tempfile
from unittest.mock import patch
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from software_limits import game_move_time, DEFAULT_MOVE_TIME_MS
from board_diagnostics import assess


class SpecificationTests(unittest.TestCase):
    def test_game_search_budget_and_invalid_overrides(self):
        self.assertEqual(game_move_time("2000"), 2000)
        self.assertEqual(game_move_time("5000"), 5000)
        self.assertEqual(game_move_time(DEFAULT_MOVE_TIME_MS), 3000)
        for bad in ["500", "1999", "5001", "10000", "abc"]:
            with self.assertRaises(argparse.ArgumentTypeError):
                game_move_time(bad)

    def test_shared_menu_preserves_local_engine_limits(self):
        from opponents import add_opponent_arguments
        parser = argparse.ArgumentParser()
        add_opponent_arguments(parser)
        args = parser.parse_args([])
        self.assertEqual((args.movetime, args.threads, args.hash_mb), (3000, 1, 16))
        self.assertIs(parser._option_string_actions["--movetime"].type, game_move_time)

    def test_target_diagnostics_requires_strict_scan_and_led_limits(self):
        timing = dict(max_us=10000, misses=0)
        platform = dict(max_us=3000, late=0, failed=0)
        good = assess(timing, platform, 10, 1000)
        self.assertTrue(good["scan_pass"] and good["led_software_pass"])
        self.assertFalse(assess(timing, platform, 10, 500)["scan_pass"])
        self.assertFalse(assess(dict(max_us=20000, misses=1), platform, 10, 1000)["scan_pass"])
        self.assertFalse(assess(timing, dict(max_us=100000, late=1, failed=0), 10, 1000)["led_software_pass"])
        self.assertFalse(assess(timing, dict(max_us=3000, late=0, failed=1), 10, 1000)["led_software_pass"])

    def test_ram_accounting_excludes_flash_and_address_padding(self):
        script = ROOT / "esp32" / "scripts" / "ram_budget.py"
        if not script.is_file():
            self.skipTest("Standalone Pi copy does not include the MCU build tools")
        spec = importlib.util.spec_from_file_location("ram_budget", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sections = """section size addr
.iram0.vectors 1024 1073741824
.iram0.text 40960 1073742848
.dram0.data 8192 1006632960
.dram0.bss 16384 1006641152
.dram0.dummy 50000 0
.flash.text 2000000 1107296256
.flash.rodata 1000000 1110000000
.rtc_noinit 32 1342177280
"""
        self.assertEqual(module.static_ram_bytes(sections), 66592)


@unittest.skipUnless((ROOT / "esp32/scripts/flash_firmware.py").is_file(), "Standalone Pi has no MCU release")
class FirmwareReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "esp32/scripts/flash_firmware.py"
        spec = importlib.util.spec_from_file_location("flash_firmware_test", path)
        cls.flash = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.flash)
        cls.release = ROOT / "esp32/release"

    def test_release_is_c5_and_dry_run_never_opens_serial(self):
        files = self.flash.validate_release(self.release)
        self.assertEqual(files[::2], ["0x2000", "0x8000", "0x10000"])
        with patch.object(self.flash, "RELEASE", self.release), \
                patch.object(self.flash.subprocess, "call") as execute, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.flash.main(["--port", "not-a-real-port", "--dry-run"]), 0)
        execute.assert_not_called()
        self.assertIn("--chip esp32c5", output.getvalue())
        self.assertIn("--no-stub", output.getvalue())

    def test_corrupt_or_other_chip_image_is_rejected(self):
        for other_chip in [False, True]:
            with self.subTest(other_chip=other_chip), tempfile.TemporaryDirectory() as directory:
                temp = Path(directory)
                for name in ["flash_manifest.json", "bootloader.bin", "partitions.bin", "firmware.bin"]:
                    shutil.copy2(self.release / name, temp / name)
                path = temp / "firmware.bin"
                data = bytearray(path.read_bytes())
                if other_chip:
                    struct.pack_into("<H", data, 12, 9)  # ESP32-S3 executable, with a matching checksum.
                    manifest = json.loads((temp / "flash_manifest.json").read_text())
                    next(item for item in manifest["images"] if item["file"] == "firmware.bin")["sha256"] = hashlib.sha256(data).hexdigest()
                    (temp / "flash_manifest.json").write_text(json.dumps(manifest))
                else:
                    data[-1] ^= 1
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, "not an ESP32-C5" if other_chip else "checksum mismatch"):
                    self.flash.validate_release(temp)

    def test_previous_chip_bootloader_address_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            for name in ["flash_manifest.json", "bootloader.bin", "partitions.bin", "firmware.bin"]:
                shutil.copy2(self.release / name, temp / name)
            manifest = json.loads((temp / "flash_manifest.json").read_text())
            next(item for item in manifest["images"] if item["file"] == "bootloader.bin")["offset"] = "0x0"
            (temp / "flash_manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "flash address"):
                self.flash.validate_release(temp)


if __name__ == "__main__":
    unittest.main()

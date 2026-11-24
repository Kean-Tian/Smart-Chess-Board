"""Compile pin maps and compare them with the exported PCB V2 KiCad evidence.

No serial ports or GPIO are opened. connections.json records BOTH the schematic
and the mismatching motor pad nets in the supplied PCB layout.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "hardware/pcb_v2/connections.json"


@unittest.skipUnless(FIXTURE.exists() and (ROOT / "esp32/main/board_pins.h").exists(),
                     "Standalone Pi copy has no PCB/MCU source evidence")
class PcbMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads(FIXTURE.read_text())

    def compile_map(self, *, named=False, pcb=True):
        source = r'''
#include "board_pins.h"
#include "scb/led_grid.h"
#include <stdio.h>
int main(void) {
    unsigned columns[] = SCB_COLUMN_PINS;
    printf("address %u %u %u\n", SCB_PIN_ROW_A0, SCB_PIN_ROW_A1, SCB_PIN_ROW_A2);
    printf("columns"); for(unsigned i=0;i<8;++i) printf(" %u",columns[i]); puts("");
    printf("motor %u %u %u %u %u %u\n",SCB_PIN_X_STEP,SCB_PIN_X_DIR,
        SCB_PIN_Y_STEP,SCB_PIN_Y_DIR,SCB_PIN_MOTOR_EN,SCB_PIN_MAGNET);
    printf("links %u %u %u %u %u\n",SCB_PIN_LED,SCB_PIN_USB_DM,SCB_PIN_USB_DP,
        SCB_PIN_UART_TX,SCB_PIN_UART_RX);
    ScbLedGrid grid;scb_led_grid_init(&grid);
    printf("led_order");for(unsigned i=0;i<64;++i)printf(" %d",scb_led_index(&grid,i));puts("");
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "probe.c").write_text(source)
            # Match ESP-IDF's generated configuration, including header load order.
            (p / "sdkconfig.h").write_text(
                ("#define CONFIG_SCB_SENSOR_NAMED_WIRING 1\n" if named else "") +
                ("#define CONFIG_SCB_MOTOR_PCB_ROUTING 1\n" if pcb else "#define CONFIG_SCB_MOTOR_PCB_ROUTING 0\n"))
            args = [os.environ.get("CC", "cc"), "-std=c17", "-Wall", "-Wextra", "-Werror",
                    "-DESP_PLATFORM=1", "-I", str(p),
                    "-I", str(ROOT / "esp32/main"), "-I", str(ROOT / "esp32/components/board_logic/include")]
            subprocess.run(args + [str(p / "probe.c"), str(ROOT / "esp32/components/board_logic/src/led_grid.c"),
                                   "-o", str(p / "probe")], check=True, capture_output=True)
            output = subprocess.check_output([str(p / "probe")], text=True)
        return {line.split()[0]: list(map(int, line.split()[1:])) for line in output.splitlines()}

    def test_straight_idc_sensor_mapping_follows_physical_connector_pins(self):
        actual = self.compile_map()
        b = self.board
        def gpio_for_sensor(name):
            pin = next(p for p, net in b["sensor_J1"].items() if net == name)
            return b["master_gpio_by_net"][b["master_J4"][pin]]
        self.assertEqual(actual["address"], [gpio_for_sensor(f"MUX_IN{i}") for i in range(1, 4)])
        self.assertEqual(actual["columns"], [gpio_for_sensor(f"DIG_OUT{i}") for i in range(1, 9)])
        # Power, ground and LED really are compatible on a straight cable.
        for pin in ("9", "10", "12", "14", "16"):
            self.assertEqual(b["master_J4"][pin], b["sensor_J1"][pin])

    def test_motor_variants_match_schematic_and_recorded_pcb_difference(self):
        names = ("X_STEP", "X_DIR", "Y_STEP", "Y_DIR", "MOTOR_EN", "EM_CTRL")
        for pcb, key in ((False, "master_gpio_by_net"), (True, "master_pcb_gpio_by_net")):
            self.assertEqual(self.compile_map(pcb=pcb)["motor"], [self.board[key][name] for name in names])
        differences = self.board["pcb_schematic_mismatches"]
        self.assertEqual({d["pad"] for d in differences}, {"39", "40", "41", "42"})

    def test_native_usb_uart_and_all_64_leds_match_netlist(self):
        actual, b = self.compile_map(), self.board
        self.assertEqual(actual["links"], [b["master_gpio_by_net"][name] for name in
                         ("LED_IN_3V3", "/USB_DN", "/USB_DP", "/UART_TX", "/UART_RX")])
        self.assertTrue(b["master_J5"]["1"].startswith("unconnected-"))
        indices = {int(ref[2:])-1: index for index, ref in enumerate(b["led_chain"])}
        self.assertEqual(actual["led_order"], [indices[q] for q in range(64)])
        self.assertEqual(len(set(actual["led_order"])), 64)


if __name__ == "__main__": unittest.main()

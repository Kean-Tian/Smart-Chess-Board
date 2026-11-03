"""Fail the firmware build if static internal RAM exceeds the control budget.

This is a static allocation check; dynamic task/driver allocations are monitored
using PLATFORM heap/min_heap. It is not the Pi Stockfish search-memory budget.
"""
import subprocess


def static_ram_bytes(output):
    prefixes = (".dram0.", ".iram0.", ".rtc.", ".rtc_noinit")
    total = 0
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 3 or not fields[0].startswith(prefixes):
            continue
        if fields[0].endswith((".dummy", ".heap")):
            continue
        total += int(fields[1])
    return total


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", required=True)
    parser.add_argument("--size-tool", required=True)
    args = parser.parse_args()
    output = subprocess.check_output([args.size_tool, "--format=sysv", args.elf], text=True)
    used = static_ram_bytes(output)
    limit = 264 * 1024
    if not used or used > limit:
        raise SystemExit(f"Static internal RAM check failed: {used} / {limit} bytes")
    print(f"SCB static internal RAM: {used} / {limit} bytes (264 KiB control ceiling)")


if __name__ == "__main__":
    main()

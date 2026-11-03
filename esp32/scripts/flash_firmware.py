"""Validate and flash the packaged FireBeetle C5 images; never force chip mismatch."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import struct
import subprocess
import sys

RELEASE = Path(__file__).resolve().parents[1] / 'release'
C5_IMAGE_CHIP_ID = 23
FLASH_BYTES = 4 * 1024 * 1024


def validate_release(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'flash_manifest.json').read_text())
    if (manifest.get('chip'), manifest.get('flash_size'), manifest.get('flash_mode'),
            manifest.get('flash_freq')) != ('esp32c5', '4MB', 'dio', '80m'):
        raise ValueError('Expected the C5 / 4 MB DIO 80 MHz release')
    images = manifest.get('images', [])
    expected = {'bootloader.bin': 0x2000, 'partitions.bin': 0x8000, 'firmware.bin': 0x10000}
    if len(images) != len(expected) or {item['file'] for item in images} != set(expected):
        raise ValueError('Unexpected image set')
    previous_end = 0
    files = []
    for item in sorted(images, key=lambda image: int(image['offset'], 0)):
        name, offset = item['file'], int(item['offset'], 0)
        path = directory / name
        data = path.read_bytes()
        if offset != expected[name] or offset < previous_end or offset + len(data) > FLASH_BYTES:
            raise ValueError(f'Invalid flash address/range: {name}')
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError(f'Release checksum mismatch: {name}')
        if name != 'partitions.bin':
            if len(data) < 24 or data[0] != 0xE9 or struct.unpack_from('<H', data, 12)[0] != C5_IMAGE_CHIP_ID:
                raise ValueError(f'Image is not an ESP32-C5 executable: {name}')
        previous_end = offset + len(data)
        files.extend([hex(offset), str(path)])
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='Actual USB serial port')
    parser.add_argument('--dry-run', action='store_true', help='Validate and print command only')
    args = parser.parse_args(argv)
    files = validate_release(RELEASE)
    command = [sys.executable, '-m', 'esptool', '--chip', 'esp32c5', '--port', args.port,
               '--baud', '460800', '--no-stub', 'write_flash', '--flash_mode', 'dio', '--flash_freq', '80m',
               '--flash_size', '4MB', *files]
    print(shlex.join(command), flush=True)
    if args.dry_run:
        print('Validated release; no serial port opened and nothing flashed.')
        return 0
    return subprocess.call(command)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(f'Cannot flash release: {exc}')

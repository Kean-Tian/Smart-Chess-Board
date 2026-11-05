"""Export an ESP-IDF ESP32-S2-Saola-1 build with verified flash metadata."""
import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from ram_budget import static_ram_bytes


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=ROOT / 'build')
    args = parser.parse_args()
    build = args.build_dir.resolve()
    description = json.loads((build / 'project_description.json').read_text())
    flash = json.loads((build / 'flasher_args.json').read_text())
    settings = flash['flash_settings']
    if description['target'] != 'esp32s2' or settings['flash_size'] != '4MB':
        raise SystemExit('Expected an ESP32-S2-Saola-1 / 4 MB build; refusing to package')
    elf = build / description['app_elf']
    source_files = [ROOT / 'CMakeLists.txt', ROOT / 'sdkconfig.defaults', ROOT / 'partitions.csv']
    source_files += sorted((ROOT / 'main').glob('*.[ch]'))
    source_files += [ROOT / 'main/CMakeLists.txt', ROOT / 'components/board_logic/CMakeLists.txt']
    source_files += sorted((ROOT / 'components/board_logic').rglob('*.[ch]'))
    if any(p.stat().st_mtime > elf.stat().st_mtime for p in source_files):
        raise SystemExit('Sources changed after the ELF was built; rebuild before packaging')
    compiler = Path(description['c_compiler'])
    size_tool = compiler.with_name(compiler.name.replace('gcc', 'size'))
    sections = subprocess.check_output([str(size_tool), '--format=sysv', str(elf)], text=True)
    used = static_ram_bytes(sections)
    if not 0 < used <= 264 * 1024:
        raise SystemExit('Static RAM budget check failed')
    out = ROOT / 'release'
    out.mkdir(exist_ok=True)
    images = []
    for offset, name in sorted(flash['flash_files'].items(), key=lambda item: int(item[0], 0)):
        source = build / name
        target_name = 'firmware.bin' if source.name == description['app_bin'] else source.name
        if 'partition' in target_name:
            target_name = 'partitions.bin'
        target = out / target_name
        shutil.copy2(source, target)
        images.append(dict(offset=offset, file=target.name, bytes=target.stat().st_size,
                           sha256=digest(target)))
    shutil.copy2(elf, out / 'firmware.elf')
    version_text = (Path(description['idf_path']) / 'tools/cmake/version.cmake').read_text()
    version_parts = dict(re.findall(r'set\(IDF_VERSION_(MAJOR|MINOR|PATCH) (\d+)\)', version_text))
    idf_version = '.'.join(version_parts[part] for part in ['MAJOR', 'MINOR', 'PATCH'])
    manifest = dict(chip='esp32s2', board='ESP32-S2-Saola-1',
                    module='ESP32-S2-WROOM/WROVER (PSRAM disabled)', idf_version=idf_version,
                    use_stub=flash['extra_esptool_args']['stub'],
                    flash_mode=settings['flash_mode'], flash_freq=settings['flash_freq'],
                    flash_size=settings['flash_size'], hardware_tested=False, images=images,
                    build_date=str(datetime.date.today()), static_internal_ram_bytes=used,
                    static_ram_limit_bytes=264 * 1024,
                    source_sha256={str(p.relative_to(ROOT)): digest(p) for p in source_files})
    (out / 'flash_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    from flash_firmware import validate_release
    validate_release(out)
    print(f'Packaged ESP32-S2-Saola-1 release: {len(images)} images, static internal RAM {used} bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

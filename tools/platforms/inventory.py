"""Hash every declared product and count actual PE/ELF/Mach-O exports."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/abi'))
from check_exports import inspect_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('specification', type=Path, help='JSON array with platform, arch, path, source_revision and kind')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    expected = set(json.loads((ROOT / 'tools/abi/contract.json').read_text(encoding='utf-8'))['symbols'])

    def native(data, required):
        result = []
        for part in inspect_bytes(data):
            symbols = part['symbols']
            missing = sorted(expected - symbols) if required else []
            if missing:
                raise ValueError('missing baseline ABI exports: ' + ', '.join(missing))
            result.append({'format': part['format'], 'machine': part['machine'], 'exports': len(symbols),
                           'exr_exports': sum(s.startswith('exr_') for s in symbols),
                           'baseline_contract_found': len(expected & symbols), 'missing': missing})
        return result

    reports = []
    for item in json.loads(args.specification.read_text(encoding='utf-8')):
        path = Path(item['path'])
        data = path.read_bytes()
        report = dict(item, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        if path.suffix in ('.aar', '.apk'):
            members = []
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if name.endswith('.so'):
                        blob = archive.read(name)
                        members.append({'path': name, 'sha256': hashlib.sha256(blob).hexdigest(),
                                        'slices': native(blob, Path(name).name == 'libexreader.so')})
            if not members:
                raise ValueError('container has no native libraries: ' + str(path))
            report.update(export_symbol_count=None, embedded_libraries=members)
        else:
            slices = native(data, item['kind'] == 'engine')
            report.update(slices=slices, export_symbol_count=sum(p['exports'] for p in slices))
        reports.append(report)
        print(item['platform'], item['arch'], path.name, report['sha256'], report['export_symbol_count'])
    args.out.write_text(json.dumps({'baseline_abi_symbols': len(expected), 'artifacts': reports}, indent=2) + '\n', encoding='utf-8')
    args.out.with_name('SHA256SUMS.txt').write_text(''.join(f"{r['sha256']}  {r['platform']}/{r['arch']}/{Path(r['path']).name}\n" for r in reports), encoding='utf-8')


if __name__ == '__main__':
    main()

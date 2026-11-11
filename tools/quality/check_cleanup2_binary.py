"""Check acceptance command literals in product/test PE binaries, including UTF-16.

Usage: python tools/quality/check_cleanup2_binary.py BEFORE PRODUCT TEST OUTPUT_JSON
GNU strings/strip must be on PATH. Stripping affects temporary audit copies only.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def strings(path):
    return [line for flags in ([], ['-el']) for line in
            subprocess.check_output(['strings', '-n', '3', *flags, str(path)], text=True, errors='replace').splitlines()]


def main():
    before, product, test, output = (Path(x).resolve() for x in sys.argv[1:])
    sources = [ROOT / 'examples/windows/shell_drive_test.inc', *sorted((ROOT / 'examples/windows').glob('*_drive.inc'))]
    commands = sorted({c for source in sources for c in
                       re.findall(r'!strcmp\(action,\s*"([a-z_0-9]+)"', source.read_text(encoding='utf-8'))})
    rows = []
    with tempfile.TemporaryDirectory(prefix='exreader-binary-audit-') as folder:
        for label, original in [('before', before), ('product', product), ('test', test)]:
            raw = strings(original)
            audit = Path(folder) / (label + '.exe')
            shutil.copy2(original, audit)
            subprocess.run(['strip', str(audit)], check=True)
            literals = strings(audit)
            rows.append(dict(build=label, bytes=original.stat().st_size,
                             sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
                             raw_drive_lines=sum('drive' in x.lower() for x in raw),
                             literal_drive_lines=[x for x in literals if 'drive' in x.lower()],
                             command_literals=[x for x in commands if x in literals],
                             drive_option='--drive' in literals, drive_log='drive.log' in literals))
    assert not rows[1]['command_literals'] and not rows[1]['drive_option'] and not rows[1]['drive_log'], rows[1]
    assert set(rows[2]['command_literals']) == set(commands), (commands, rows[2]['command_literals'])
    result = dict(commands_checked=len(commands), commands=commands, builds=rows,
                  note='Raw COFF symbols can share names with commands; temporary stripped copies distinguish literals. The remaining literal drive is a CRT path-error field.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({**result, 'commands': len(commands)}, indent=2))


if __name__ == '__main__':
    main()

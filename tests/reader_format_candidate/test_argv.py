"""Exercise the exact thin adapter without an SDK; invoked again in full producers."""
import json
from pathlib import Path
import subprocess
import sys
from common import actions, write, file_hash, identity


def main():
    actions(); binary = Path(sys.argv[1]).resolve(); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    suffix = '.exe' if sys.platform == 'win32' else ''
    probe, native = binary / ('format-argv-probe' + suffix), binary / ('format-argv-self-test' + suffix)
    vectors = [[], [''], ['ASCII'], ['Бретёр', 'портрет'], ['😀', '漢字'], ['é', 'e\u0301'],
               ['space in value', '"quoted"', 'trailing\\'], ['--query', '', '--file', 'C:/space dir/book.fb2']]
    checks = []
    for index, values in enumerate(vectors):
        done = subprocess.run([str(probe), *values], capture_output=True, check=True)
        (out / f'argv-{index}.stdout').write_bytes(done.stdout); (out / f'argv-{index}.stderr').write_bytes(done.stderr)
        actual = json.loads(done.stdout.decode('utf-8'))['argv_hex']
        expected = [value.encode('utf-8').hex() for value in values]
        assert actual == expected, (index, actual, expected)
        checks.append({'case': index, 'argv_hex': actual, 'ok': True})
    done = subprocess.run([str(native)], capture_output=True, check=True)
    (out / 'utf16.stdout').write_bytes(done.stdout); (out / 'utf16.stderr').write_bytes(done.stderr)
    report = json.loads(done.stdout.decode('utf-8'))
    if sys.platform == 'win32':
        assert report['windows_utf16_checks'] == 5 and report['invalid_rejected_without_fallback'] is True
    result = {**identity(), 'ok': True, 'platform': sys.platform, 'vectors': checks, 'native_utf16': report,
              'probe_sha256': file_hash(probe), 'native_test_sha256': file_hash(native)}
    write(out / 'report.json', result); print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == '__main__': main()

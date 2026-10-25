"""Actions-only: actual Android owner exports the NULL-expression negative graph for macOS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'reader_android_raw3'))
from bundle import parse, safe, sha  # noqa: E402

PACKAGE = 'org.exreader.host'


def adb(*args, timeout=120):
    return subprocess.check_output(['adb', *map(str, args)], stderr=subprocess.STDOUT, timeout=timeout)


def private(name):
    return adb('exec-out', 'run-as', PACKAGE, 'cat', 'files/' + name)


def push(file, relative):
    name = safe(relative)
    temporary = '/data/local/tmp/c07-' + hashlib.sha256(name.encode()).hexdigest()
    adb('push', file, temporary)
    adb('exec-out', 'run-as', PACKAGE, 'mkdir', '-p', 'files/' + str(Path(name).parent))
    adb('exec-out', 'run-as', PACKAGE, 'cp', temporary, 'files/' + name)


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    identity = {key: os.environ[name] for key, name in (('source_sha', 'GITHUB_SHA'), ('run_id', 'GITHUB_RUN_ID'), ('attempt', 'GITHUB_RUN_ATTEMPT'))}
    adb('shell', 'am', 'force-stop', PACKAGE)
    assert adb('shell', 'pm', 'clear', PACKAGE).strip() == b'Success'
    adb('shell', 'am', 'start', '-W', '-n', PACKAGE + '/.MainActivity')
    adb('shell', 'am', 'force-stop', PACKAGE)
    manifest = parse((args.fixtures / 'manifest.json').read_bytes())
    for row in manifest['books']:
        push(args.fixtures / row['file'], 'preferences-fixtures/' + row['file'])
    local = args.output / 'private-input.json'
    local.write_bytes(json.dumps(manifest, ensure_ascii=False).encode())
    push(local, 'preferences-input.json')
    local.unlink()
    adb('shell', 'am', 'force-stop', PACKAGE)
    adb('logcat', '-c')
    command = ['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'phase', 'c07-null-export']
    for key, value in identity.items():
        command.extend(('-e', key, value))
    command.append(PACKAGE + '.test/' + PACKAGE + '.Raw3InteropTest')
    done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1500, check=False)
    (args.output / 'instrumentation.txt').write_bytes(done.stdout)
    body = private('raw3-interop-c07-null-export.json')
    (args.output / 'raw-report.json').write_bytes(body)
    (args.output / 'logcat.txt').write_bytes(adb('logcat', '-d', '-v', 'threadtime', '-t', '5000'))
    report = parse(body)
    assert done.returncode == 0 and b'INSTRUMENTATION_CODE: -1' in done.stdout, done.stdout.decode(errors='replace')[-4000:]
    assert report['passed'] is True and report['phase'] == 'c07-null-export' and all(report.get(k) == v for k, v in identity.items())
    assert [row['name'] for row in report['checks']] == ['c07_android_actual_null_negative_export_for_mac'] and all(row['pass'] for row in report['checks'])
    bundle = args.output / 'null-bundle'
    raw = private('c07-null-outgoing/manifest.json')
    exported = parse(raw)
    (bundle).mkdir(parents=True, exist_ok=True)
    (bundle / 'manifest.json').write_bytes(raw)
    for row in exported['originals'] + exported['revisions']:
        target = bundle / safe(row['file'])
        target.parent.mkdir(parents=True, exist_ok=True)
        data = private('c07-null-outgoing/' + row['file'])
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
        target.write_bytes(data)
    (args.output / 'result.json').write_text(json.dumps({**identity, 'accepted': True, 'phase': report['phase'], 'pid': report['pid'],
        'manifest_sha256': sha(raw), 'null_revision': exported['null_revision']}, indent=2) + '\n')
    print(json.dumps({**identity, 'c07_android_null_export': True, 'manifest_sha256': sha(raw)}), flush=True)


if __name__ == '__main__':
    main()

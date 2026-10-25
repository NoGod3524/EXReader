"""Actions-only exact original APK replay. Its outputs grant no acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

assert os.environ.get('GITHUB_ACTIONS') == 'true'
folder = Path('build/android-fixed-pan-replay')
logs = folder / 'logs'
logs.mkdir(exist_ok=True)
package = 'org.exreader.host'

def adb(*args, input=None, timeout=90):
    return subprocess.check_output(['adb', *map(str, args)], input=input, stderr=subprocess.STDOUT, timeout=timeout)

adb('install', '-r', '-t', folder / 'host.apk')
adb('install', '-r', '-t', folder / 'probe.apk')
assert adb('shell', 'pm', 'clear', package).strip() == b'Success'
adb('shell', 'am', 'start', '-W', '-n', package + '/.MainActivity')
adb('shell', 'am', 'force-stop', package)
adb('exec-out', 'run-as', package, 'mkdir', '-p', 'files/fixed-pan-fixtures')
manifest = json.loads((folder / 'fixtures/manifest.json').read_text())
for row in manifest['books']:
    original = folder / 'fixtures' / row['file']
    data = original.read_bytes()
    assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
    temporary = '/data/local/tmp/reader-pan-' + row['file']
    adb('push', original, temporary)
    adb('exec-out', 'run-as', package, 'cp', temporary, 'files/fixed-pan-fixtures/' + row['file'])
adb('shell', f"run-as {package} sh -c 'cat > files/fixed-pan-input.json'", input=json.dumps(manifest, ensure_ascii=False).encode())
adb('logcat', '-c')
process = subprocess.run(['adb', 'shell', 'am', 'instrument', '-w', '-r', '-e', 'phase', 'first',
                          '-e', 'source_sha', 'd199f0dc67ed929ad7c5a3fe8edb855ef50f1f67',
                          '-e', 'run_id', os.environ['GITHUB_RUN_ID'], '-e', 'attempt', os.environ['GITHUB_RUN_ATTEMPT'],
                          package + '.test/' + package + '.FixedPanUiTest'], capture_output=True, timeout=1200)
(logs / 'instrumentation.txt').write_bytes(process.stdout + process.stderr)
print(process.stdout.decode(errors='replace'), flush=True)
for buffer in ('main', 'crash', 'system'):
    data = adb('logcat', '-d', '-b', buffer, '-v', 'threadtime', '-t', '5000')
    (logs / (buffer + '-logcat.txt')).write_bytes(data)
    if buffer == 'crash':
        print(data.decode(errors='replace'), flush=True)
raw = subprocess.run(['adb', 'exec-out', 'run-as', package, 'cat', 'files/fixed-pan-ui-first.json'], capture_output=True, timeout=30)
(logs / 'raw-report.txt').write_bytes(raw.stdout)
print(raw.stdout.decode(errors='replace'), flush=True)
result = {'diagnostic_only': True, 'accepted': False, 'original_source': 'd199f0dc67ed929ad7c5a3fe8edb855ef50f1f67',
          'original_run': 40146403326, 'original_artifact': 12580498901, 'replay_run': os.environ['GITHUB_RUN_ID'],
          'instrumentation_returncode': process.returncode, 'report_read_returncode': raw.returncode}
(logs / 'diagnostic.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)

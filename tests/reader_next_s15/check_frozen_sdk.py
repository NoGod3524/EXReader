"""Actions-only proof that the module default still targets the frozen SDK 3.40.

Builds the same module source against the real frozen 3.40 install, exports a
real original through the installed C consumer, and shows the approved 3.41 pin
is refused by that graph. Runs only on GitHub Actions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
parser = argparse.ArgumentParser()
parser.add_argument('--sdk', required=True)
parser.add_argument('--module-src', required=True)
parser.add_argument('--stage', required=True)
parser.add_argument('--consumer', required=True)
parser.add_argument('--fixtures', required=True)
parser.add_argument('--work', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
sdk = Path(args.sdk).resolve(); module_src = Path(args.module_src).resolve()
stage = Path(args.stage).resolve(); consumer = Path(args.consumer).resolve()
fixtures = Path(args.fixtures).resolve(); work = Path(args.work).resolve()
output = Path(args.output).resolve()
work.mkdir(parents=True, exist_ok=True); output.parent.mkdir(parents=True, exist_ok=True)
summary = {'accepted': False, 'platform': os.environ['RUNNER_OS'], 'source_sha': os.environ['GITHUB_SHA'],
           'run_id': int(os.environ['GITHUB_RUN_ID']), 'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
           'checks': [], 'failures': [], 'cases': {}, 'sdk': {}, 'limitations': []}


def require(v, m):
    if not v: raise AssertionError(m)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cmake(args, name, expect_fail=False, markers=()):
    log = work / (name + '.log')
    proc = subprocess.run([os.environ.get('CMAKE_EXECUTABLE', 'cmake')] + [str(a) for a in args],
                          capture_output=True, text=True, timeout=1800)
    log.write_text(''.join(['$ cmake ' + ' '.join(str(a) for a in args) + '\n', proc.stdout, proc.stderr]), encoding='utf-8')
    text = proc.stdout + proc.stderr
    case = {'exit': proc.returncode, 'log': log.name, 'markers': {m: (m in text) for m in markers}}
    if expect_fail:
        require(proc.returncode != 0, name + ' unexpectedly succeeded')
        missing = [m for m in markers if m not in text]
        require(not missing, name + ' did not fail for the intended reason, missing ' + repr(missing))
        case['refused'] = True
    else:
        require(proc.returncode == 0, name + ' failed: ' + text[-4000:])
        case['refused'] = False
    summary['cases'][name] = case


def passcase(name): summary['checks'].append(name)


try:
    base = (sdk / 'include/exr/base.h').read_text()
    version = re.search(r'#define EXR_VERSION "([0-9.]+)"', base)
    abi = re.search(r'#define EXR_ABI_VERSION ([0-9]+)u', base)
    require(version and version.group(1) == '3.40.0', 'install is not the frozen 3.40 SDK')
    require(abi and abi.group(1) == '1', 'frozen install ABI is not 1')
    require('set(EXReader_VERSION "3.40.0")' in (sdk / 'lib/cmake/EXReader/EXReaderConfig.cmake').read_text(),
            'frozen EXReaderConfig version')
    summary['sdk'] = {'version': version.group(1), 'abi': int(abi.group(1))}
    passcase('frozen_sdk_340_install_identity')

    cmake(['-S', module_src, '-B', work / 'module-default', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
           '-DCMAKE_PREFIX_PATH=' + str(sdk), '-DCMAKE_INSTALL_PREFIX=' + str(stage)], 'module_default_pin_accepted')
    cmake(['--build', work / 'module-default', '--parallel', '4'], 'module_default_build')
    cmake(['--install', work / 'module-default'], 'module_default_install')
    config = (stage / 'lib/cmake/EXReaderOriginalExport/EXReaderOriginalExportConfig.cmake').read_text()
    require('find_dependency(EXReader 3.40.0 EXACT CONFIG COMPONENTS library)' in config,
            'default install does not pin the frozen 3.40.0 graph')
    passcase('frozen_sdk_default_pin_accepted')

    cmake(['-S', module_src, '-B', work / 'module-341', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
           '-DCMAKE_PREFIX_PATH=' + str(sdk), '-DEXR_SDK_VERSION=3.41.0'], 'explicit_341_refused', expect_fail=True,
          markers=['EXReader', '3.41.0'])
    passcase('frozen_sdk_explicit_341_refused')

    cmake(['-S', consumer, '-B', work / 'consumer', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
           '-DS15_PROBE_CONSUMER=OFF', '-DCMAKE_PREFIX_PATH=' + str(stage) + ';' + str(sdk)], 'consumer_configure')
    cmake(['--build', work / 'consumer', '--parallel', '4'], 'consumer_build')
    exe = 'original-export-c-consumer' + ('.exe' if os.name == 'nt' else '')
    binary = work / 'consumer' / exe
    require(binary.is_file(), 'installed C consumer binary')
    selfcheck = subprocess.run([str(binary)], capture_output=True, timeout=120)
    require(selfcheck.returncode == 0, 'C ABI link: ' + selfcheck.stderr.decode(errors='replace'))
    identity = json.loads(selfcheck.stdout)
    require(identity['version'] == '3.40.0' and identity['abi'] == 1 and identity['c_abi'] == 1, 'frozen C ABI identity')
    passcase('frozen_sdk_c_abi_link')

    source = work / 'fixture.txt'; shutil.copyfile(fixtures / 'book.txt', source)
    db = work / 'library.db'; target = work / 'export'; target.mkdir()
    first = subprocess.run([str(binary), 'seed', str(db), str(target), str(source)], capture_output=True, timeout=300)
    require(first.returncode == 0, 'frozen export: ' + first.stderr.decode(errors='replace'))
    item = json.loads(first.stdout)
    require(item['hash'] == sha(source) and item['bytes'] == source.stat().st_size, 'frozen original hash/size')
    require(Path(item['path']).read_bytes() == source.read_bytes(), 'frozen original bytes')
    passcase('frozen_sdk_original_byte_identity')
    second = subprocess.run([str(binary), str(db), str(target)], capture_output=True, timeout=300)
    require(second.returncode == 0, 'frozen duplicate export failed')
    dup = json.loads(second.stdout)
    require(dup['created'] == 0 and dup['hash'] == item['hash'] and Path(dup['path']).read_bytes() == source.read_bytes(),
            'existing frozen target overwritten or recreated')
    require(len([p for p in target.iterdir()]) == 1, 'duplicate export left extra files')
    passcase('frozen_sdk_existing_target_not_overwritten')
    summary['accepted'] = True
except Exception as exc:
    summary['failures'].append(repr(exc))
finally:
    summary['binary'] = {'path': str(work / 'consumer'), 'platform': os.environ['RUNNER_OS']}
    summary['count'] = len(summary['checks'])
    output.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)
raise SystemExit(0 if summary['accepted'] else 1)

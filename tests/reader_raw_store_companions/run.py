"""Actions only. Preserve the sealed core semantics; replace its ownership boundary."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types
from appendices import APPENDICES

ROOT = Path(__file__).resolve().parents[2]
BASE = '0737d03c1316295a210aa527833c05054d29c1d4'
OUT = ROOT / 'build/raw-store-companions'
MODULES = ('commands', 'sync', 'session')
CORE = ROOT / 'tests/reader_selector_bytes/run.py'

def guard_companions():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()
    assert git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA']
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    changes = git('diff', '--name-only', BASE, 'HEAD').splitlines()
    allowed = tuple('apps/reader/' + m + '/' for m in MODULES) + ('tests/reader_raw_store_companions/',)
    assert all(p.startswith(allowed) or p in APPENDICES or p in {'.github/workflows/reader-raw-store-companions.yml',
        'docs/READER-RAW-STORE-COMPANIONS.md', 'docs/validation/reader-raw-store-companions.json'} for p in changes), changes
    core_paths = git('ls-tree', '-r', '--name-only', BASE, '--',
                     *['apps/reader/' + p for p in ('revisions', 'reading-state', 'reading-commands', 'annotation-view')]).splitlines()
    for path in core_paths:
        original = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)
        current = (ROOT / path).read_bytes()
        if path in APPENDICES:
            # Git's checkout newline conversion is ignored, all other bytes exact.
            assert current.replace(b'\r\n', b'\n').rstrip(b'\n') == (original.replace(b'\r\n', b'\n') + APPENDICES[path].encode()).rstrip(b'\n'), path
        else:
            assert current.replace(b'\r\n', b'\n') == original.replace(b'\r\n', b'\n'), path
    subprocess.run(['git', 'diff', '--exit-code', BASE, 'HEAD', '--',
                    'tests/reader_selector_bytes', 'tests/reader_commands', 'tests/reader_sync', 'tests/reader_session',
                    'extras', 'examples', 'apps/reader/store', 'src', 'include', 'cmake', 'CMakeLists.txt'], cwd=ROOT, check=True)
    original = subprocess.check_output(['git', 'show', BASE + ':tests/reader_selector_bytes/run.py'], cwd=ROOT)
    assert original == CORE.read_bytes()
    return hashlib.sha256(original).hexdigest()

def main():
    core_sha = guard_companions()
    # These are exactly the sealed independent-package ownership statements;
    # all SDK, original-regression, raw capture and behavioral assertions stay.
    source = CORE.read_text(encoding='utf-8')
    first = source.index("    changed = run(['git', 'diff', '--name-only', BASE, 'HEAD'])")
    last = source.index("    pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'", first)
    replaced = source[first:last]
    assert 'allowed = tuple' in replaced and 'assert all(' in replaced
    assert 'protocol(' not in replaced and 'build(' not in replaced
    patched = source[:first] + '    guard_companions()\n' + source[last:]
    core = types.ModuleType('sealed_core');core.__file__ = str(CORE)
    core.__dict__['guard_companions'] = guard_companions
    exec(compile(patched, str(CORE), 'exec'), core.__dict__)
    core.main()
    core_out = core.OUT
    OUT.mkdir(parents=True)
    core.OUT = OUT
    run, build = core.run, core.build
    product, sdk = core_out / 'product-stage', ROOT / 'build/reading-library/stage'
    dav = OUT / 'dav-stage'
    build(ROOT / 'extras/webdav', 'dav', dav)
    stages = {}
    for label, enabled in [('off', False), ('candidate', True)]:
        stage = OUT / (label + '-stage')
        shutil.copytree(core_out / (label + '-stage'), stage)
        stages[label] = stage
        prefixes = ';'.join(map(str, [stage, dav, product, sdk]))
        for module in MODULES:
            build(ROOT / 'apps/reader' / module, label + '-' + module, stage,
                  ['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF'), '-DCMAKE_PREFIX_PATH=' + prefixes])
    def consume(relative, name, stage):
        return build(ROOT / relative, name, stage,
                     ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [stage, dav, product, sdk]))], False)
    off = stages['off']
    for archive in off.glob('lib/*'):
        if archive.suffix in {'.a', '.lib'}:
            assert b'_raw_v3' not in archive.read_bytes(), archive
    old_cmd = consume('tests/reader_commands/consumer', 'off-command-consumer', off)
    old_rev = consume('tests/reader_revisions/consumer', 'off-revision-consumer', off)
    old_sync = consume('tests/reader_sync/consumer', 'off-sync-consumer', off)
    old_session = consume('tests/reader_session/consumer', 'off-session-consumer', off)
    joint_reading = consume('tests/reader_reading_commands/consumer', 'off-joint-reading-consumer', off)
    raw = consume('tests/reader_raw_store_companions', 'raw-consumers', stages['candidate'])
    suffix = core.SUFFIX
    exe = lambda folder, name: folder / (name + suffix)
    for label, command, ccommand, revision, mapping, log in [
        ('off', exe(old_cmd, 'command-consumer'), exe(old_cmd, 'command-c-consumer'), exe(old_rev, 'revision-consumer'),
         old_cmd / 'command-link.map', OUT / 'off-command-consumer-build.log'),
        ('raw', exe(raw, 'raw-commands'), exe(raw, 'raw-commands-c'), exe(raw, 'raw-revision'),
         raw / 'raw-commands.map', OUT / 'raw-consumers-build.log')]:
        run([sys.executable, ROOT / 'tests/reader_commands/check_commands.py', '--consumer', command, '--c-consumer', ccommand,
             '--revision-consumer', revision, '--product-prefix', product, '--link-map', mapping,
             '--build-log', log, '--output', OUT / (label + '-command-regression')], label + '-command-regression', 420)
    for label, sync, session, revision in [
        ('off', exe(old_sync, 'sync-consumer'), exe(old_session, 'session-consumer'), exe(old_rev, 'revision-consumer')),
        ('raw', exe(raw, 'raw-sync'), exe(raw, 'raw-session'), exe(raw, 'raw-revision'))]:
        for module, checker, program in [('reader_sync', 'check_sync.py', sync), ('reader_session', 'check_session.py', session)]:
            name = label + '-' + module
            run([sys.executable, ROOT / 'tests' / module / checker, '--consumer', program, '--revision-consumer', revision,
                 '--output', OUT / name], name, 1200)
    run([exe(old_sync, 'sync-c-consumer')], 'off-sync-c')
    run([sys.executable, ROOT / 'tests/reader_reading_commands/check_reading_commands.py',
         '--probe', exe(joint_reading, 'reading-commands-probe'), '--c-consumer', exe(joint_reading, 'reading-commands-c-consumer'),
         '--fixtures', core_out / 'fixtures', '--font', ROOT / 'tests/fixtures/fonts/primary.ttf',
         '--link-map', joint_reading / 'reading-commands-link.map', '--output', OUT / 'joint-reading-regression'], 'joint-reading-regression', 420)
    # Both version-only and already-imported-target prefix mixing must fail.
    mixed = []
    for name, module, enabled, stage in [('on-rejects-old', 'commands', True, off),
                                          ('off-rejects-new', 'commands', False, stages['candidate'])]:
        p = subprocess.run(['cmake', '-S', str(ROOT / 'apps/reader' / module), '-B', str(OUT / name), '-G', 'Ninja',
                            '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF'),
                            '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [stage, dav, product, sdk]))], capture_output=True, text=True)
        (OUT / (name + '.log')).write_text(p.stdout + p.stderr)
        assert p.returncode and 'EXReaderRevisions' in p.stdout + p.stderr
        mixed.append(name)
    mix = OUT / 'mixed-import-source';mix.mkdir()
    (mix / 'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.24)\nproject(Mixed LANGUAGES C CXX)\n'
        + 'find_package(EXReaderRevisions 0.3.0 EXACT CONFIG REQUIRED PATHS "' + str(off / 'lib/cmake/EXReaderRevisions').replace('\\', '/') + '" NO_DEFAULT_PATH)\n'
        + 'set(EXReaderRevisions_DIR "' + str(stages['candidate'] / 'lib/cmake/EXReaderRevisions').replace('\\', '/') + '" CACHE PATH "" FORCE)\n'
        + 'find_package(EXReaderCommands 0.2.0 EXACT CONFIG REQUIRED PATHS "' + str(stages['candidate'] / 'lib/cmake/EXReaderCommands').replace('\\', '/') + '" NO_DEFAULT_PATH)\n')
    p = subprocess.run(['cmake', '-S', str(mix), '-B', str(OUT / 'mixed-import'), '-G', 'Ninja', '-DCMAKE_PREFIX_PATH=' + str(product)], capture_output=True, text=True)
    (OUT / 'mixed-import.log').write_text(p.stdout + p.stderr)
    assert p.returncode and 'legacy capability family' in p.stdout + p.stderr
    mixed.append('already-imported-target-refused')
    import profiles
    profiles.check(core, OUT, stages['candidate'], off, product, sdk, dav)
    run([sys.executable, ROOT / 'tests/reader_raw_store_companions/tls.py', '--programs', raw,
         '--core', core_out, '--old-revision', exe(old_rev, 'revision-consumer'), '--output', OUT / 'actual-tls'], 'actual-tls', 900)
    reports = {}
    for folder in ['off-command-regression', 'raw-command-regression', 'off-reader_sync', 'raw-reader_sync',
                   'off-reader_session', 'raw-reader_session']:
        report = json.loads((OUT / folder / 'result.json').read_text())
        assert report['accepted']
        reports[folder] = report['count']
    result = {'accepted': True, 'adopted': False, 'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
              'attempt': os.environ['GITHUB_RUN_ATTEMPT'], 'platform': sys.platform, 'core_template_sha256': core_sha,
              'ownership_replacement_sha256': hashlib.sha256(replaced.encode()).hexdigest(), 'original_regressions': reports,
              'mixed_profiles_refused': mixed, 'scope': 'explicit commands/sync/session raw-store companion candidate only',
              'actual_hosts': False, 'physical_device': False, 'complete_product': False, 'off_new_symbols_absent': True}
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)

if __name__ == '__main__':
    main()

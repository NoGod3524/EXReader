"""Actions-only builds, original regressions, real capture processes and protocol cases."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/selector-bytes'
BASE = 'b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7'
LEGACY = '210403d121d6484a8fff4ea7ffd911efa3163535'
PDF_SHA = '5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc'
MODULES = ['revisions', 'reading-state', 'reading-commands', 'annotation-view']
SUFFIX = '.exe' if os.name == 'nt' else ''
ENV = dict(os.environ)

def run(args, name=None, timeout=1800):
    args = list(map(str, args))
    print('RUN', ' '.join(args), flush=True)
    p = subprocess.run(args, cwd=ROOT, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if name:
        (OUT / (name + '.log')).write_text(p.stdout, encoding='utf-8')
    print(p.stdout[-12000:], flush=True)
    if p.returncode:
        raise RuntimeError((args, p.returncode))
    return p.stdout

def archive(sha, name, *paths):
    target = OUT / name
    target.mkdir()
    raw = subprocess.run(['git', 'archive', sha, *paths], cwd=ROOT, capture_output=True, check=True).stdout
    import io
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        tar.extractall(target, filter='data')
    return target

def build(source, name, prefix, extra=(), install=True):
    target = OUT / name
    run(['cmake', '-S', source, '-B', target, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_INSTALL_PREFIX=' + str(prefix), *extra], name + '-configure')
    run(['cmake', '--build', target, '--parallel', '4'], name + '-build')
    if install:
        run(['cmake', '--install', target], name + '-install')
    return target

def module_family(source, name, enabled, product, sdk):
    prefix = OUT / (name + '-stage')
    for module in MODULES:
        build(source / 'apps/reader' / module, name + '-' + module, prefix,
              ['-DEXR_READER_SELECTOR_BYTES_CANDIDATE=' + ('ON' if enabled else 'OFF'),
               '-DEXR_SDK_VERSION=3.41.0', '-DEXR_SDK=' + str(sdk),
               '-DREADER_PRODUCT_PREFIX=' + str(product),
               '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [prefix, product, sdk]))])
    return prefix

def protocol(probe, work):
    fixture = json.loads((work / 'bookmark.json').read_text())
    cases = []
    def check(name, edit, valid=False):
        value = copy.deepcopy(fixture)
        edit(value)
        path = work / ('protocol-' + str(len(cases)) + '.json')
        path.write_text(json.dumps(value, separators=(',', ':')), encoding='utf-8')
        text = run([probe, 'protocol', path, work], 'protocol-' + str(len(cases)), 30)
        status = int(text.split('STATUS ')[-1].splitlines()[0])
        assert (status == 0) == valid, (name, status)
        cases.append({'name': name, 'status': status, 'pass': True})
    def selector(v): return v['payload']['location']['selector']
    def raw(v, name, data): selector(v)[name] = {'base64': base64.b64encode(data).decode(), 'size': len(data)}
    check('genuine NUL point', lambda v: None, True)
    check('unknown version', lambda v: v['payload']['location'].update(anchor_version=4))
    check('wrong v3 mode', lambda v: v['payload']['location'].update(mode='reflow_global'))
    for value in ['!!==', 'AA A', 'AA\nA', 'AA-_', 'A===', 'AA=A', 'AAA', 'AAAA=', 'AB==', 'AAB=']:
        check('noncanonical Base64 ' + repr(value), lambda v, s=value: selector(v).update(prefix={'base64': s, 'size': 1 if len(s) == 4 and s.endswith('==') else 2}))
    check('mismatched size', lambda v: selector(v)['suffix'].update(size=1))
    check('NULL with bytes', lambda v: selector(v).update(prefix={'base64': None, 'size': 1}))
    check('NULL and allocated empty preserved by format', lambda v: selector(v).update(prefix={'base64': None, 'size': 0}, exact={'base64': '', 'size': 0}), True)
    check('NULL exact expression is valid transport', lambda v: selector(v).update(exact={'base64': None, 'size': 0}), True)
    check('64KiB exact allowed only raw path', lambda v: (raw(v, 'exact', b'a' * 65536), selector(v).update(start=0, end=65536)), True)
    check('65537 exact refused', lambda v: (raw(v, 'exact', b'a' * 65537), selector(v).update(start=0, end=65537)))
    check('context 128 bytes and 32 scalars', lambda v: raw(v, 'prefix', '🙂'.encode() * 32), True)
    check('context 129 bytes', lambda v: raw(v, 'prefix', b'a' * 129))
    check('context 33 scalars', lambda v: raw(v, 'prefix', b'a' * 33))
    check('invalid decoded UTF8', lambda v: raw(v, 'prefix', b'\xff'))
    check('NUL scalar allowed', lambda v: raw(v, 'prefix', b'\0'), True)
    check('identifier NUL stays forbidden', lambda v: v['payload']['location'].update(page_id='page\0-1'))
    check('ordinary JSON string limit unchanged', lambda v: v['payload'].update(text='a' * 65537))
    check('extra raw key rejected', lambda v: selector(v)['prefix'].update(extra=0))
    check('negative size', lambda v: selector(v)['prefix'].update(size=-1))
    check('float size', lambda v: selector(v)['prefix'].update(size=0.0))
    check('span mismatch', lambda v: selector(v).update(end=1))
    return cases

def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    OUT.mkdir(parents=True)
    run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'])
    run(['git', 'diff', '--exit-code', 'edddc463c06ed5731195cdb8f06b2df6dff7699e', 'HEAD', '--', 'src', 'include', 'cmake', 'CMakeLists.txt'])
    run(['git', 'diff', '--exit-code', BASE, 'HEAD', '--', 'apps/reader/store', 'examples', 'tests/fixtures'])
    changed = run(['git', 'diff', '--name-only', BASE, 'HEAD']).splitlines()
    allowed = tuple('apps/reader/' + x + '/' for x in MODULES) + ('tests/reader_selector_bytes/',)
    assert all(p.startswith(allowed) or p in {'.github/workflows/reader-selector-bytes.yml',
        'docs/READER-SELECTOR-BYTES-CANDIDATE.md', 'docs/validation/reader-selector-bytes-candidate.json'} for p in changed), changed
    pdf = ROOT / 'tests/fixtures/pdf-public-text.pdf'
    assert len(pdf.read_bytes()) == 8845 and hashlib.sha256(pdf.read_bytes()).hexdigest() == PDF_SHA
    product = OUT / 'product-stage'
    build(ROOT / 'apps/reader/store/native', 'product', product)
    run(['cmake', '--preset', 'reading-library'], 'sdk-configure')
    run(['cmake', '--build', '--preset', 'reading-library'], 'sdk-build', 2400)
    run(['cmake', '--install', 'build/reading-library'], 'sdk-install')
    sdk = ROOT / 'build/reading-library/stage'
    original = archive(BASE, 'original-source', 'apps/reader', 'extras/opds')
    baseline = module_family(original, 'baseline', False, product, sdk)
    off = module_family(ROOT, 'off', False, product, sdk)
    candidate = module_family(ROOT, 'candidate', True, product, sdk)
    programs = {}
    for name, prefix in [('baseline', baseline), ('off', off), ('candidate', candidate)]:
        consumer = build(ROOT / 'tests/reader_selector_bytes', name + '-consumer', prefix,
                         ['-DRAW_SELECTOR_CONSUMER=' + ('ON' if name == 'candidate' else 'OFF'),
                          '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [prefix, product, sdk]))], False)
        programs[name] = consumer / ('selector-bytes' + SUFFIX)
        run([programs[name], 'legacy', pdf, OUT / (name + '-legacy')], name + '-legacy')
    for filename in ['v1-wire.json', 'v2-wire.json']:
        expected = (OUT / 'baseline-legacy' / filename).read_bytes()
        assert expected == (OUT / 'off-legacy' / filename).read_bytes() == (OUT / 'candidate-legacy' / filename).read_bytes()
    work = OUT / 'actual'
    for phase in ['seed', 'receive', 'reopen']:
        run([programs['candidate'], phase, pdf, work], 'actual-' + phase, 120)
    protocol_cases = protocol(programs['candidate'], work)
    # Complete original v1/v2 probes are built from unchanged original sources.
    legacy = archive(LEGACY, 'legacy-source', 'apps/reader/revisions', 'extras/opds')
    old = OUT / 'legacy-stage'
    build(legacy / 'apps/reader/revisions', 'legacy-revisions', old, ['-DREADER_PRODUCT_PREFIX=' + str(product)])
    build(original / 'apps/reader/reading-state', 'legacy-state', old,
          ['-DEXR_SDK_VERSION=3.41.0', '-DEXR_SDK=' + str(sdk), '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [old, product, sdk]))])
    old_probe = build(ROOT / 'tests/reader_reading_state/consumer', 'legacy-consumer', old,
          ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [old, product, sdk]))], False)
    v2 = build(ROOT / 'tests/reader_reading_v2/consumer', 'v2-consumer', off,
          ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [off, product, sdk]))], False)
    fixtures = OUT / 'fixtures'
    run([sys.executable, ROOT / 'tests/reader_reading_state/make_fixtures.py', fixtures], 'fixtures')
    run([sys.executable, ROOT / 'tests/reader_reading_v2/check_sdk.py', '--probe', v2 / ('reading-v2-probe' + SUFFIX),
         '--legacy-probe', old_probe / ('reading-state-probe' + SUFFIX), '--legacy-c-consumer', old_probe / ('reading-state-c-consumer' + SUFFIX),
         '--fixtures', fixtures, '--font', ROOT / 'tests/fixtures/fonts/primary.ttf', '--legacy-map', old_probe / 'reading-state-link.map',
         '--link-map', v2 / 'reading-v2-link.map', '--output', OUT / 'original-sdk-regression'], 'original-sdk-regression', 240)
    # Full old reading-command and typed-view regressions on the new default OFF build.
    build(original / 'apps/reader/commands', 'off-commands', off,
          ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [off, product]))])
    for module, checker, executable in [('reader_reading_commands', 'check_reading_commands.py', 'reading-commands'),
                                         ('reader_annotation_view', 'check_annotation_view.py', 'annotation-view')]:
        consumer = build(ROOT / 'tests' / module / 'consumer', module + '-consumer', off,
              ['-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, [off, product, sdk]))], False)
        args = [sys.executable, ROOT / 'tests' / module / checker,
                '--probe', consumer / (executable + '-probe' + SUFFIX), '--c-consumer', consumer / (executable + '-c-consumer' + SUFFIX),
                '--link-map', consumer / (executable + '-link.map'), '--output', OUT / module]
        if module == 'reader_reading_commands':
            args += ['--fixtures', fixtures, '--font', ROOT / 'tests/fixtures/fonts/primary.ttf']
        run(args, module, 420)
    logs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.log')}
    result = {'accepted': True, 'scope': 'explicit core codec/revisions/commands/typed-view candidate only',
              'source_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
              'platform': sys.platform, 'pdf_sha256': PDF_SHA, 'pdf_bytes': 8845, 'protocol_checks': protocol_cases,
              'legacy_wire_bytes_unchanged': True, 'original_regressions_passed': True, 'logs': logs,
              'actual_android_apple_interop': False, 'adopted': False, 'physical_device': False, 'complete_product': False}
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)

if __name__ == '__main__':
    main()

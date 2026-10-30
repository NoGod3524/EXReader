"""C09 Windows/macOS final-program provider audit entrypoint. Runs only in GitHub Actions.

guard     additions-only source scope against the exact base
selftest  py_compile of every owned file plus synthetic protocol cases
windows   audit the real final Windows program of the unchanged tests/windows_sdk342/build.py recipe
macos     audit the real final macOS program of the unchanged tests/apple_sdk342_package/run.py recipe

Nothing here grants F07 or six-platform acceptance; a platform without real evidence stays pending.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/reader_provider_desktop_remaining_20261030'))
import pd_audit as P  # noqa: E402
import pd_core as C  # noqa: E402


def windows_config():
    out = C.ROOT.resolve() / 'build/windows-sdk342'
    host = out / 'host'
    return dict(sdk_version='3.42.0', image=host / 'EXReaderWave3.exe', package_image=out / 'package/EXReader/EXReader.exe',
                package_dir=out / 'package/EXReader', map=host / 'windows-host.map', link_cwd=host, sdk=out / 'sdk',
                product=[out / 'product', out / 'raw'], lib_dirs=os.environ.get('LIB', '').split(';'))


def macos_config():
    out = C.ROOT.resolve() / 'build/apple-sdk342/macos'
    host = out / 'host'
    app = host / 'EXReader.app'
    return dict(sdk_version='3.42.0', image=app / 'Contents/MacOS/EXReader', map=host / 'product-link.map', sdk=out / 'sdk',
                products=out / 'products', host=host, frameworks=app / 'Contents/Frameworks')


def show(result, out):
    print('platform:', result['platform'], 'passed:', result['passed'], 'evidence_complete:', result['evidence_complete'], flush=True)
    print('image:', json.dumps(result['image'], sort_keys=True)[:1500], flush=True)
    print('map:', json.dumps(result['map'], sort_keys=True)[:600], flush=True)
    print('selected members:', result['selected_members'], 'archives inspected:', result['archives_inspected'],
          'installed libraries:', result['installed_libraries'], flush=True)
    print('sqlite reference classification:', json.dumps(P.sqlite_classes(result), sort_keys=True), flush=True)
    print('finding kinds:', json.dumps(result['finding_kinds'], sort_keys=True), flush=True)
    for finding in result['findings'][:40]:
        print('finding:', json.dumps(finding, sort_keys=True)[:400], flush=True)
    for control in result['negative_controls']:
        print('negative control:', control['name'], 'expected', control['expected_kind'], 'rejected', control['rejected'],
              control.get('error', ''), flush=True)
    print('dynamic needed:', json.dumps(result['dynamic_needed']), flush=True)
    print('runtime identity:', json.dumps(result['runtime_identity'], sort_keys=True)[:1500], flush=True)
    print('imports:', json.dumps(result['imports'], sort_keys=True), flush=True)
    print('weak definitions:', json.dumps(result['weak_definitions'], sort_keys=True), flush=True)
    print('pending kinds:', json.dumps(sorted({p['kind'] for p in result['pending']})), flush=True)
    for pending in result['pending'][:25]:
        print('pending:', json.dumps(pending, sort_keys=True)[:700], flush=True)
    evidence = json.loads((out / 'evidence.json').read_text())
    print('roles:', json.dumps(evidence['roles'], sort_keys=True), flush=True)
    print('product catalog archives:', json.dumps(evidence['product_catalog_archives']), flush=True)
    for row in evidence['installed_libraries'][:120]:
        print('installed:', row['role'], row['size'], row['sha256'][:16], row['path'], flush=True)
    owners = sorted({tuple(x) for x in evidence['selected'] if x[0] not in ()})
    print('selected archives:', json.dumps(sorted({a for a, _ in owners}))[:6000], flush=True)


def main():
    C.actions_only()
    command = sys.argv[1]
    if command == 'guard':
        C.save(C.OUT / 'source.json', C.guard())
        return
    if command == 'selftest':
        owned = sorted(Path(C.ROOT / C.OWNED).glob('*.py'))
        subprocess.check_call([sys.executable, '-m', 'py_compile', *map(str, owned), str(C.ROOT / C.AUDITOR)])
        subprocess.check_call([sys.executable, str(C.ROOT / C.OWNED / 'test_pd.py')])
        return
    config = {'windows': windows_config, 'macos': macos_config}[command]()
    out = C.OUT / command
    collect = {'windows': P.collect_windows, 'macos': P.collect_macos}[command]
    report = dict(C.identity(command, config['sdk_version']), passed=False)
    try:
        result = collect(config, out)
    except Exception as error:
        report['failure'] = str(error)
        C.save(out / 'result.json', report)
        raise
    show(result, out)
    C.require(result['passed'], 'provider audit findings or failed negative controls: %s' % json.dumps(result['finding_kinds']))


if __name__ == '__main__':
    main()

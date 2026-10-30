"""C05 final-image provider/map auditor entrypoint. Runs only in GitHub Actions.

guard      additions-only source scope against the exact base
selftest   synthetic protocol cases (no native inspection)
linux      audit the real final retained GTK host after tests/gtk_sdk342_package/run.py build
collect    audit any platform from a JSON config (see fp_collect.collect)
aggregate  bind per-platform result.json files; never grants acceptance
"""
import json
import re
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/reader_final_provider_20261030'))
import fp_collect as K  # noqa: E402
import fp_core as C  # noqa: E402


def linux_config():
    root = C.ROOT.resolve()
    host = root / 'build/gtk-raw-wave3/retained-host'
    archives = sorted(str(p) for base in ('build/reading-library/stage', 'build/gtk-raw-wave3/raw-stage', 'build/original-hash') for p in (root / base).rglob('*.a'))
    archives += sorted(str(p) for p in host.rglob('*.a'))
    exports = sorted((root / 'build/gtk-raw-wave3/raw-stage').rglob('EXReaderProductCatalogTargets*.cmake'))
    names = sorted({n for e in exports for n in re.findall(r'/(lib[\w.+-]+\.a)"', e.read_text())})
    C.save(C.OUT / 'linux/installed-archives.json', dict(archives=archives, product_catalog_exports=[str(e) for e in exports], product_catalog_archives=names))
    C.require(names and all(any(a.endswith('/' + n) for a in archives) for n in names), 'ProductCatalog export archives not installed: %s' % names)
    return dict(platform='linux', sdk_version='3.42.0', image=str(host / 'gtk-host/exreader-linux'),
        map=str(host / 'gtk-account-host.map'), map_format='gnu', product_catalog_archives=names, link_cwd=str(host), archives=archives,
        roles=dict(sdk=[str(root / 'build/reading-library/stage') + '/'], product=[str(root / 'build/gtk-raw-wave3/raw-stage') + '/'], hash=[str(root / 'build/original-hash') + '/'],
                   host=[str(host) + '/'], system=['/usr/lib/', '/lib/', '/usr/lib64/', '/lib64/']))


def main():
    C.actions_only()
    command = sys.argv[1]
    if command == 'guard':
        C.save(C.OUT / 'source.json', C.guard())
    elif command == 'selftest':
        subprocess.check_call([sys.executable, '-m', 'py_compile', *map(str, sorted(Path(C.ROOT / C.OWNED).glob('*.py'))), str(C.ROOT / C.AUDITOR)])
        subprocess.check_call([sys.executable, str(C.ROOT / C.OWNED / 'test_fp.py')])
        subprocess.check_call([sys.executable, str(C.ROOT / C.OWNED / 'test_retro.py')])
    elif command == 'retro':
        import fp_retro
        fp_retro.main()
    elif command in ('linux', 'collect'):
        config = linux_config() if command == 'linux' else json.loads(Path(sys.argv[2]).read_text())
        out = C.OUT / config['platform']
        report = dict(C.identity(config['platform'], config.get('sdk_version')), passed=False, findings=None)
        try:
            report = K.collect(config, out)
        except Exception as error:
            report['failure'] = str(error)
            C.save(out / 'result.json', report)
            raise
        from collections import Counter
        print('sqlite reference classification:', dict(Counter(r['status'] for r in report['sqlite_references'])))
        print('pending (explicit, not waived):', json.dumps(report['pending'], sort_keys=True)[:1500])
        print('unselected sqlite candidate roles:', dict(Counter(c['role'] for r in report['sqlite_references'] for c in r['unselected_candidates'])))
        if not report['passed']:
            from collections import Counter
            print('finding kinds:', dict(Counter(f['kind'] for f in report['findings'])))
            for f in report['findings'][:60]:
                print('finding:', json.dumps(f, sort_keys=True)[:300])
        C.require(report['passed'], 'provider/map audit findings: %d' % len(report['findings']))
    elif command == 'aggregate':
        results = {}
        for path in sorted(Path(sys.argv[2]).rglob('result.json')):
            row = json.loads(path.read_text())
            results[row['platform']] = row
        C.save(C.OUT / 'aggregate.json', C.bind_results(results))
    else:
        raise ValueError(command)


if __name__ == '__main__':
    main()

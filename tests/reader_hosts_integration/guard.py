"""Actions-only exact merge provenance; production bytes stay pinned."""
import json
import os
from pathlib import Path
import subprocess

BASE = '33167f2faa6cabae6656b8c1089a799dc7e5549e'
SDK = '9854061be331fe603a1822d9b2b36ee357154927'
DELIVERIES = {
    'g1': '3bcc6511c928665c0889a33bc98cf5e1bfadaccc',
    'windows_search': '12f4f06cae2115fba90d3d43ebb0c291ea11e99a',
    'gtk_reading': '401729ba9537b58c8566372fb953384ce61381d7',
    'android_reading': '5d7da81495e545901f7fc802af00e0b779d1d8c4',
}
ALLOWED = (
    'tests/reader_hosts_integration/', '.github/workflows/reader-hosts-integration.yml',
    'tests/reader_windows_search/verify.py', 'tests/reader_windows_search/check_ui.py',
    'docs/READER-HOSTS-INTEGRATION.md',
    'docs/validation/reader-hosts-integration.json',
)


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only'
    sha = os.environ['GITHUB_SHA']
    assert git('rev-parse', 'HEAD') == sha
    for source in [BASE, *DELIVERIES.values()]:
        subprocess.run(['git', 'merge-base', '--is-ancestor', source, sha], check=True)
    subprocess.run(['git', 'diff', '--exit-code', SDK, sha, '--', 'src', 'include', 'cmake',
                    'CMakeLists.txt', 'tests/fixtures', 'bindings', '.github/workflows/native.yml',
                    '.github/workflows/reliability.yml'], check=True)
    subprocess.run(['git', 'diff', '--exit-code', DELIVERIES['g1'], sha, '--',
                    'apps/reader/store/001_catalog.sql'], check=True)
    for path in git('diff', '--name-only', BASE, sha).splitlines():
        assert any(path.startswith(p) if p.endswith('/') else path == p for p in ALLOWED), path
    # The only adopted module delta from G1 is Android's tested no-replace
    # export publication. Neither the SDK nor the shared anchor codec changes.
    for path in ('apps', 'examples', 'extras'):
        subprocess.run(['git', 'diff', '--exit-code', BASE, sha, '--', path], check=True)
    report = dict(source_sha=sha, run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], accepted=True, baseline=BASE,
                  deliveries=DELIVERIES, sdk_changed=False, schema_changed=False)
    target = Path('build/hosts-input.json');target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

"""Actions-only exact merge provenance; production bytes stay pinned."""
import json
import os
from pathlib import Path
import subprocess

BASE = 'e0c28defc7f2113cb4ccdab5dfe1d2b072915a82'
SDK = '9854061be331fe603a1822d9b2b36ee357154927'
DELIVERIES = {
    'g1': '3bcc6511c928665c0889a33bc98cf5e1bfadaccc',
    'windows_search': '12f4f06cae2115fba90d3d43ebb0c291ea11e99a',
    'gtk_reading': '401729ba9537b58c8566372fb953384ce61381d7',
    'android_reading': '5d7da81495e545901f7fc802af00e0b779d1d8c4',
    'windows_navigation': '89252d4f1377c37917b2ad59cf54faa8103d6b67',
    'android_preferences': '91270f8e7b5a3085430992b97dd27f612666480a',
    'android_cbz_reading': '6b43e83537aa6b03bda889d258fe73c0e317acb1',
    'windows_reading_records': '2dcd325b31590bbb5374842e6c7f26fa2dcedd21',
}
ALLOWED = (
    'tests/reader_hosts_integration/', '.github/workflows/reader-hosts-integration.yml',
    'tests/reader_windows_search/verify.py', 'tests/reader_windows_search/check_ui.py',
    'tests/reader_windows_navigation/verify.py',
    'tests/reader_windows_records/verify.py',
    # Root-reviewed chooser input driver; native production bytes stay pinned.
    'tests/reader_gtk_preferences/retain_account.py',
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
    # Native host changes are pinned to the exact ordinary-merge production
    # tree. Only verifier/workflow/docs edits follow this reviewed merge.
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

# SPDX-License-Identifier: MIT
"""Actions-only macOS adoption with complete same-source desktop regressions."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import download_artifact_zip, fetch, pages, require


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'cloud only')
    run_id, attempt, source = int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT']), os.environ['GITHUB_SHA']
    out = Path(sys.argv[1]); out.mkdir(parents=True)
    summary = {'accepted': False, 'source_sha': source, 'run_id': run_id, 'attempt': attempt,
               'artifacts': [], 'jobs': [], 'platforms': {}, 'problems': [], 'sdk_changed': False,
               'schema_changed': False, 'ios_accepted': False, 'android_accepted': False,
               'host_ui_accepted': False, 'six_platform_accepted': False, 'complete_product': False}
    try:
        run = fetch(f'actions/runs/{run_id}')
        require(run['head_sha'] == source and run['run_attempt'] == attempt and run['path'] == '.github/workflows/reader-sync-apple.yml', 'caller differs')
        jobs = pages(f'actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
        artifacts = pages(f'actions/runs/{run_id}/artifacts', 'artifacts')
        suites = [('sync-source-evidence', 77), ('sync-protocol-evidence', 59), ('sync-evidence', 33),
                  ('projection-evidence', 32), ('commands-evidence', 33), ('metadata-evidence', 29), ('session-evidence', 20)]
        canonical = {}
        for platform, runner, native in [('Linux', 'ubuntu-22.04', 'linux'), ('Windows', 'windows-2022', 'win32'), ('macOS', 'macos-15', 'darwin')]:
            selected = [j for j in jobs if j['name'] == f'native / installed typed product commands ({runner})']
            require(len(selected) == 1, 'missing/duplicate producer ' + platform); job = selected[0]
            require(job['head_sha'] == source and job['run_attempt'] == attempt and job['conclusion'] == 'success', 'producer failed or differs ' + platform)
            selected = [a for a in artifacts if a['name'] == f'reader-commands-{platform}-{run_id}-{attempt}']
            require(len(selected) == 1, 'missing/duplicate artifact ' + platform); artifact = selected[0]
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and artifact['workflow_run']['head_sha'] == source, 'artifact differs ' + platform)
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream); stream.seek(0); data = stream.read()
            require(len(data) == artifact['size_in_bytes'] and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'ZIP bytes/digest differ ' + platform)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                counts = {}
                for suite, count in suites:
                    report = json.loads(archive.read(suite + '/result.json'))
                    require(report.get('accepted') is True and report['source_sha'] == source and int(report['run_id']) == run_id and int(report['attempt']) == attempt and report['platform'] == native, 'report identity/refusal ' + suite)
                    if suite == 'sync-source-evidence' and platform == 'Windows': count = 76
                    checks = report['checks']
                    ids = [c['id'] if isinstance(c, dict) else c for c in checks]
                    require(len(checks) == count and len(set(ids)) == count and all(not isinstance(c, dict) or c.get('pass') is True for c in checks), 'suite cases missing/refused ' + suite)
                    counts[suite] = count
                    if suite != 'sync-source-evidence':
                        if suite in canonical: require(ids == canonical[suite], 'platform case coverage differs ' + suite)
                        else: canonical[suite] = ids
                suffix = '.exe' if platform == 'Windows' else ''
                for suite, binary in [('sync-source-evidence', 'sync-dav-consumer/webdav-consumer'),
                                      ('sync-protocol-evidence', 'sync-revision-consumer/revision-consumer'),
                                      ('session-evidence', 'session-consumer/session-consumer')]:
                    report = json.loads(archive.read(suite + '/result.json'))
                    require(hashlib.sha256(archive.read(binary + suffix)).hexdigest() == report['consumer_sha256'], 'consumer hash differs ' + suite)
                source_report = json.loads(archive.read('sync-source-evidence/result.json'))
                if platform == 'macOS':
                    dependencies = source_report['consumer_native_dependencies']
                    require('/usr/lib/libcurl.4.dylib' in dependencies and not any(s in dependencies.lower() for s in ('webview', 'webkit', 'chromium', 'libcrypto', 'libssl')), 'Apple native transport dependency differs')
                    require('OpenSSL::Crypto' not in archive.read('sync-stage/lib/cmake/EXReaderSync/EXReaderSyncTargets.cmake').decode(), 'Apple sync still exports OpenSSL dependency')
                summary['platforms'][platform] = counts
            summary['jobs'].append({k: job[k] for k in ('id', 'name', 'conclusion')})
            summary['artifacts'].append({k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        summary['accepted'] = True
    except Exception as error:
        summary['problems'].append(str(error))
    (out / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)
    raise SystemExit(0 if summary['accepted'] else 1)


if __name__ == '__main__': main()

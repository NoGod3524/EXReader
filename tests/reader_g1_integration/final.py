"""Authenticate both strict summaries and current upstream results in Actions."""
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
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source, run, attempt = os.environ['GITHUB_SHA'], int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT'])
    output = Path('build/g1-summary')
    output.mkdir(parents=True, exist_ok=True)
    result = dict(accepted=False, source_sha=source, run_id=run, attempt=attempt, artifacts=[], problems=[],
                  scope='three-desktop installed module composition and retained native Windows account/UIA scopes',
                  complete_product=False, cycle_complete=False, gtk_accepted=False, android_accepted=False,
                  ios_accepted=False, accessibility_accepted=False, performance_accepted=False)
    try:
        needs = json.loads(os.environ['RESULTS'])
        require(set(needs) == {'compose', 'aggregate', 'account', 'windows-summary'}, 'missing upstream result')
        require(all(row['result'] == 'success' for row in needs.values()), 'an upstream job failed')
        metadata = fetch('actions/runs/%d' % run)
        require(metadata['head_sha'] == source and metadata['run_attempt'] == attempt and
                metadata['path'] == '.github/workflows/reader-g1-integration.yml', 'workflow identity differs')
        artifacts = pages('actions/runs/%d/artifacts' % run, 'artifacts')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run, attempt), 'jobs')
        for stem, job_name, leaf in [
            ('reader-module-composition-report', 'strict same-source composition report', 'result.json'),
            ('reader-windows-account-summary', 'strict same-source summary', 'verified.json')]:
            name = '%s-%d-%d' % (stem, run, attempt)
            matches = [a for a in artifacts if a['name'] == name]
            require(len(matches) == 1, 'missing/duplicate summary ' + name)
            artifact = matches[0]
            job = [j for j in jobs if j['name'] == job_name]
            require(len(job) == 1 and job[0]['conclusion'] == 'success' and job[0]['head_sha'] == source,
                    'summary job failed or differs')
            require(not artifact['expired'] and artifact['size_in_bytes'] > 0 and
                    artifact['workflow_run']['id'] == run and artifact['workflow_run']['head_sha'] == source,
                    'artifact expired or differs')
            with tempfile.TemporaryFile() as stream:
                download_artifact_zip(artifact['id'], stream)
                stream.seek(0)
                data = stream.read()
            require(len(data) == artifact['size_in_bytes'] and
                    'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'summary ZIP differs')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                matches = [p for p in archive.namelist() if p == leaf or p.endswith('/' + leaf)]
                require(len(matches) == 1, 'summary payload is missing or duplicate')
                report = json.loads(archive.read(matches[0]))
            require(report['accepted'] is True and report.get('problems') == [] and report['source_sha'] == source and
                    str(report['run_id']) == str(run) and str(report['attempt']) == str(attempt),
                    'summary is not accepted on this source and attempt')
            if stem == 'reader-module-composition-report':
                require(set(report['platforms']) == {'linux', 'windows', 'macos'}, 'missing platform')
                require(all(p.get('g1_initial', {}).get('accepted') is True and
                            p.get('g1_relocated', {}).get('accepted') is True for p in report['platforms'].values()),
                        'extended common-source scope missing')
            else:
                require(report['counts'].get('ui158') == 158 and report['counts'].get('account') == 32 and
                        report['counts'].get('a11y') == 24, 'native Windows counts differ')
            result['artifacts'].append({k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        result['accepted'] = True
    except Exception as error:
        result['problems'].append(str(error))
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Binds the three GTK reports, both packaged programs and the artifact identity to this run and attempt."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD = ROOT / 'build/c10-download'
OUT = ROOT / 'build/c10-authentication'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    run, attempt, source = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], os.environ['GITHUB_SHA']
    identity = dict(source_sha=source, run_id=run, attempt=attempt, linux_job_result=os.environ.get('LINUX_RESULT'),
                    artifact_id=os.environ.get('ARTIFACT_ID'), artifact_upload_digest=os.environ.get('ARTIFACT_DIGEST'),
                    verified=False)
    problems = []
    try:
        listing = json.loads(subprocess.check_output(
            ['gh', 'api', 'repos/%s/actions/runs/%s/artifacts' % (os.environ['GITHUB_REPOSITORY'], run)], text=True))
        name = 'c10-gtk-wave3-%s-%s' % (run, attempt)
        match = [row for row in listing['artifacts'] if row['name'] == name]
        assert len(match) == 1, 'artifact count %d' % len(match)
        artifact = match[0]
        identity['artifact'] = dict(id=artifact['id'], name=artifact['name'], size_in_bytes=artifact['size_in_bytes'],
                                    digest=artifact.get('digest'), expires_at=artifact['expires_at'], expired=artifact['expired'])
        assert str(artifact['id']) == str(identity['artifact_id'])
        programs = dict(wave3=DOWNLOAD / 'compact-package/EXReader-Linux/bin/exreader-linux',
                        off=DOWNLOAD / 'off-package/EXReader-Linux/bin/exreader-linux')
        identity['programs'] = {key: sha(path) for key, path in programs.items()}
        reports = {}
        for key, path in (('wave3', DOWNLOAD / 'wave3-ui/report.json'),
                          ('compact', DOWNLOAD / 'compact-ui/report.json'),
                          ('g13', DOWNLOAD / 'g13/result.json')):
            report = json.loads(path.read_text(encoding='utf-8'))
            assert report['source_sha'] == source and str(report['run_id']) == run and str(report['attempt']) == attempt, key
            reports[key] = dict(accepted=report.get('accepted', report.get('pass', report.get('search_scope_passed'))),
                                count=report.get('count'),
                                program_sha256=report.get('program_sha256'), report_sha256=sha(path))
        identity['reports'] = reports
        assert reports['wave3']['program_sha256'] == identity['programs']['wave3']
        assert reports['compact']['program_sha256'] == identity['programs']['wave3']
        assert reports['g13']['program_sha256'] == identity['programs']['off']
        identity['verified'] = True
    except BaseException as error:  # noqa: BLE001 - recorded, then the job fails
        problems.append(repr(error))
    identity['problems'] = problems
    (OUT / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(identity, indent=2))
    if problems:
        sys.exit('artifact identity could not be bound')


if __name__ == '__main__':
    main()

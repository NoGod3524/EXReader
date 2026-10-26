"""Binds the Windows report, the exact ZIP, its EXE and the artifact identity to this run and attempt (Actions only)."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD = ROOT / 'build/c09-download'
OUT = ROOT / 'build/c09-authentication'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    run, attempt, source = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'], os.environ['GITHUB_SHA']
    identity = dict(source_sha=source, run_id=run, attempt=attempt, windows_job_result=os.environ.get('WINDOWS_RESULT'),
                    artifact_id=os.environ.get('ARTIFACT_ID'), artifact_upload_digest=os.environ.get('ARTIFACT_DIGEST'), verified=False)
    problems = []
    try:
        listing = json.loads(subprocess.check_output(
            ['gh', 'api', 'repos/%s/actions/runs/%s/artifacts' % (os.environ['GITHUB_REPOSITORY'], run)], text=True))
        name = 'c09-windows-wave3-%s-%s' % (run, attempt)
        match = [a for a in listing['artifacts'] if a['name'] == name]
        assert len(match) == 1, 'artifact count %d' % len(match)
        artifact = match[0]
        identity['artifact'] = dict(id=artifact['id'], name=artifact['name'], size_in_bytes=artifact['size_in_bytes'],
                                    digest=artifact.get('digest'), expires_at=artifact['expires_at'], expired=artifact['expired'])
        assert str(artifact['id']) == str(identity['artifact_id'])
        report = json.loads((DOWNLOAD / 'report.json').read_text(encoding='utf-8'))
        assert report['source_sha'] == source and str(report['run_id']) == run and str(report['attempt']) == attempt
        identity['report'] = dict(accepted=report['accepted'], failures=report['failures'], steps=report['steps'],
                                  compact22_checks=report.get('compact22_checks'),
                                  compact22_accepted=report.get('compact22_accepted'),
                                  retained26_checks=report.get('retained26_checks'),
                                  extracted_retained26_checks=report.get('extracted_retained26_checks'),
                                  extracted_native_ui_checks=report.get('extracted_native_ui_checks'),
                                  desktop=report.get('desktop'), wave3_ui_checks=report.get('wave3_ui_checks'))
        archive = DOWNLOAD / 'EXReader-wave3-windows.zip'
        assert archive.is_file()
        data = archive.read_bytes()
        identity['zip'] = dict(bytes=len(data), sha256=sha(data))
        assert identity['zip'] == dict(bytes=report['zip']['bytes'], sha256=report['zip']['sha256'])
        with zipfile.ZipFile(archive) as z:
            exe = z.read('EXReader/EXReader.exe')
        identity['program_sha256'] = sha(exe)
        assert identity['program_sha256'] == report['program_sha256']
        identity['verified'] = True
    except BaseException as error:  # noqa: BLE001
        problems.append(repr(error))
    identity['problems'] = problems
    (OUT / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(identity, indent=2))
    if problems:
        sys.exit('artifact identity could not be bound')


if __name__ == '__main__':
    main()

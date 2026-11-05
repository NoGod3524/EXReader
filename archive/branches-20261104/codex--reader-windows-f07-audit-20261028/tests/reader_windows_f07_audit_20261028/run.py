"""Retrospective audit/replay only. Never invoke a compiler or launch the EXE."""
import json
import os
import sys
import traceback
import zipfile
import wf07_contract as C
from wf07_evidence import api, download, extract
from wf07_native import audit


def main():
    phase = sys.argv[1]
    guarded = C.guard()
    if phase == 'guard':
        print(json.dumps(guarded)); return
    C.require(phase in ('inspect', 'authenticate', 'admit'), 'unknown operation')
    if phase == 'admit':
        report = json.loads((C.OUT / 'authentication.json').read_text())
        C.require(report['authenticated'] is True, 'not authenticated')
        C.require(report['windows_f07_accepted'] is True, 'Windows F07 remains blocked; see authenticated findings and original-external-input gap')
        return
    try:
        if phase == 'authenticate':
            C.require(os.environ['INSPECTION_RESULT'] == 'success', 'inspection producer failed; do not repeat native inspection')
        raw, inventory, source = download()
        report = audit(raw, inventory, source)
        if phase == 'authenticate':
            jobdata = api(f'actions/runs/{os.environ["GITHUB_RUN_ID"]}/attempts/{os.environ["GITHUB_RUN_ATTEMPT"]}/jobs?per_page=100')['jobs']
            jobs = [j for j in jobdata if j['name'] == 'windows-ownership-inspection']
            C.require(len(jobs) == 1 and jobs[0]['head_sha'] == os.environ['GITHUB_SHA'] and jobs[0]['conclusion'] == 'success',
                      'current audit producer identity differs')
            id_ = int(os.environ['AUDIT_ARTIFACT_ID'])
            item = api('actions/artifacts/' + str(id_))
            C.require(item['id'] == id_ and item['name'] == 'windows-ownership-' + os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT'] and
                item['expired'] is False and item['workflow_run']['head_sha'] == os.environ['GITHUB_SHA'] and
                str(item['workflow_run']['id']) == os.environ['GITHUB_RUN_ID'] and
                item['digest'] == 'sha256:' + os.environ['AUDIT_ARTIFACT_DIGEST'], 'current audit upload identity differs')
            import subprocess
            path = C.OUT / 'inspection-original.zip'
            with path.open('wb') as stream:
                subprocess.run(['gh', 'api', 'repos/NoGod3524/EXReader/actions/artifacts/' + str(id_) + '/zip'], stdout=stream, check=True)
            C.require(path.stat().st_size == item['size_in_bytes'] and 'sha256:' + C.digest(path) == item['digest'], 'audit upload byte identity differs')
            folder = C.OUT / 'inspection-original'; extract(path, folder)
            prior = json.loads((folder / 'audit.json').read_text())
            C.require(prior == report, 'independent native/manifest/map replay differs')
            C.save(C.OUT / 'authentication.json', dict(C.identity(), authenticated=True,
                windows_f07_accepted=False, full_six_platform_f07_accepted=False,
                original_capture_artifact=C.PINS['capture'][0], inspection_artifact=item,
                findings_sha256=C.digest(C.OUT / 'audit.json'), gaps=report['gaps']))
            print('Original upload authenticated and independent COFF/PE/map/header ownership replay identical. F07 remains false.', flush=True)
    except Exception as error:
        C.save(C.OUT / 'failure.json', dict(C.identity(), phase=phase, error=str(error), windows_f07_accepted=False))
        traceback.print_exc()
        raise


if __name__ == '__main__': main()

"""Actions-only strict same-run artifact and actual-program authentication."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip, require


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source, run, attempt = os.environ['GITHUB_SHA'], int(os.environ['GITHUB_RUN_ID']), int(os.environ['GITHUB_RUN_ATTEMPT'])
    out = ROOT / 'build/windows-current-common-summary'; out.mkdir(parents=True, exist_ok=True)
    result = dict(accepted=False, source_sha=source, run_id=run, attempt=attempt, artifacts={}, problems=[], complete_product=False)
    archives = []
    def identity(report):
        require(report['source_sha'] == source and str(report['run_id']) == str(run) and str(report['attempt']) == str(attempt), 'Foreign report identity')
        require(report['accepted'] is True, 'Unaccepted report')
    def artifact(key, expected_name):
        meta = fetch('actions/artifacts/' + os.environ[key + '_ID'])
        require(meta['name'] == expected_name and meta['workflow_run']['head_sha'] == source and meta['workflow_run']['id'] == run and not meta['expired'], 'Foreign/expired artifact ' + key)
        require(datetime.fromisoformat(meta['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'Expired artifact')
        with tempfile.TemporaryFile() as stream:
            download_artifact_zip(meta['id'], stream); stream.seek(0); raw = stream.read()
        digest = hashlib.sha256(raw).hexdigest()
        require(len(raw) == meta['size_in_bytes'] and meta['digest'] == 'sha256:' + digest and os.environ[key + '_DIGEST'].removeprefix('sha256:') == digest, 'ZIP digest mismatch')
        archive = zipfile.ZipFile(io.BytesIO(raw)); archives.append(archive)
        names = archive.namelist()
        require(len(names) == len(set(names)) and all(not name.startswith(('/', '\\')) and '..' not in name.replace('\\','/').split('/') for name in names), 'Unsafe ZIP members')
        result['artifacts'][key] = {k: meta[k] for k in ('id','name','size_in_bytes','digest','expires_at')}
        return archive
    try:
        needs = json.loads(os.environ['JOB_RESULTS'])
        require(set(needs) == {'search','summary','current_native','current_fonts'}, 'Required job set changed')
        result['job_results'] = {name: row['result'] for name, row in needs.items()}
        all_success = all(v['result'] == 'success' for v in needs.values())
        workflow = fetch('actions/runs/' + str(run))
        require(workflow['head_sha'] == source and workflow['path'] == '.github/workflows/reader-raw3-common-windows.yml' and workflow['head_branch'] == 'codex/dot-windows-common-gate', 'Foreign workflow/source/branch')
        jobs = fetch('actions/runs/%d/attempts/%d/jobs?per_page=100' % (run, attempt))['jobs']
        expected = {'installed F1 and native Windows search controls and lifecycle', 'same-source native Windows search artifact authentication', 'current_native', 'current_fonts'}
        for name in expected:
            producer, = [job for job in jobs if job['name'] == name]
            require(producer['head_sha'] == source and producer['run_attempt'] == attempt and producer['status'] == 'completed', 'Foreign or incomplete producer: ' + name)
            if name in ('current_native', 'current_fonts'):
                require(producer['conclusion'] == 'success' and all(step['conclusion'] in ('success','skipped') for step in producer['steps']), 'Current producer failed: ' + name)
        original = artifact('ORIGINAL', 'reader-windows-search-initial-%d-%d' % (run, attempt))
        origin = json.loads(original.read('windows-341-guard/current-source.json'))
        require(origin['source_sha'] == source and origin['authorized_common_base'] == 'aefe6107f8f073847f0ed590f0ad9602fa720f3d' and origin['authorized_sdk_source'] == '5b7a34ee4f1ce38cf3bcd7cf0220575f4ecf7da9' and str(origin['run_id']) == str(run) and str(origin['attempt']) == str(attempt), 'Current source grant missing')
        native = artifact('NATIVE', 'windows-txt-forward-scan-%d-%d' % (run, attempt))
        c09 = json.loads(native.read('c09/report.json')); identity(c09)
        require(not c09['failures'] and all(step['passed'] is True for step in c09['steps']), 'Retained C09 failure')
        forward = json.loads(native.read('txt-forward-scan/report.json')); identity(forward)
        require(not forward['failures'], 'Forward scan failure')
        require(hashlib.sha256(native.read('c09/package/EXReader/EXReader.exe')).hexdigest() == forward['candidate_sha256'], 'Candidate executable substituted')
        require(hashlib.sha256(native.read('txt-scan-reference/EXReaderWave3.exe')).hexdigest() == forward['reference_sha256'], 'Reference executable substituted')
        fonts = artifact('FONTS', 'windows-font-lifecycle-%d-%d' % (run, attempt))
        binding = json.loads(fonts.read('evidence/same-source.json')); identity(binding)
        require(binding['case_counts'] == [8,5], 'Font coverage drift')
        digest = hashlib.sha256(fonts.read('host/EXReaderWave3.exe')).hexdigest()
        require(binding['program_sha256'] == digest, 'Font host substituted')
        for name, count in [('report.json',8),('txt/report.json',5)]:
            report = json.loads(fonts.read('evidence/' + name)); identity(report)
            require(not report['problems'] and len(report['checks']) == count and all(c['passed'] is True for c in report['checks']) and report['program_sha256'] == digest, 'Font report mismatch')
        result.update(accepted=all_success, original_OFF_F3_atomic13=needs['summary']['result'] == 'success', c09=c09, forward=forward, font_binding=binding,
                      scope='Current common source: original OFF/F1/F2/records/import/account/compact/F3/atomic13, C09/TXT/from-first/SDK7, fonts8+5; separate real Windows configurations, not one substituted executable')
        if not all_success:
            result['problems'].append('Original required gates failed; current independent evidence authenticated, no overall grant')
    except Exception as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    finally:
        for archive in archives: archive.close()
        (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(result), flush=True)
    require(result['accepted'], 'Common Windows gate refused')


if __name__ == '__main__': main()

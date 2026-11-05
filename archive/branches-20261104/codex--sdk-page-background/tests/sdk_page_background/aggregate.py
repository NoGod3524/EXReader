"""Actions-only original native suites and old/new consumer ZIP authentication."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from check_parallel_integration import fetch, pages, require


def download_artifact_zip(artifact_id):
    return subprocess.check_output(['gh', 'api', 'repos/' + os.environ['GITHUB_REPOSITORY']
                                    + '/actions/artifacts/%d/zip' % artifact_id], timeout=120)


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    validator_source = os.environ['GITHUB_SHA'];validation_run = int(os.environ['GITHUB_RUN_ID'])
    selected = os.environ.get('BG_VERIFY_RUN', '')
    metadata = fetch('actions/runs/' + (selected or str(validation_run)))
    source = metadata['head_sha'];run = metadata['id'];attempt = metadata['run_attempt']
    if selected:
        subprocess.run(['git', 'merge-base', '--is-ancestor', source, validator_source], check=True)
        subprocess.run(['git', 'diff', '--exit-code', source, validator_source, '--', 'src', 'include', 'cmake',
                        'CMakeLists.txt', 'examples', 'bindings', 'tests/fixtures', 'tests/sdk_page_background/probe.c',
                        'tests/sdk_page_background/CMakeLists.txt', 'tests/sdk_page_background/make_fixture.py'], check=True)
    else:
        require(source == validator_source, 'wrong current source')
    result = dict(source_sha=source, run_id=run, attempt=attempt, accepted=False,
                  validator_source=validator_source, validation_run_id=validation_run,
                  original_programs_rechecked_without_reexecution=bool(selected),
                  complete_product=False, performance_accepted=False, host_ui_accepted=False,
                  six_platform_accepted=False, platforms={}, problems=[])
    try:
        require(metadata['head_sha'] == source and metadata['run_attempt'] == attempt
                and metadata['path'] == '.github/workflows/sdk-page-background.yml', 'foreign run')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run, attempt), 'jobs')
        artifacts = pages('actions/runs/%d/artifacts' % run, 'artifacts')
        for platform in ('linux', 'windows', 'macos'):
            job, = [j for j in jobs if j['name'] == 'background consumers (' + platform + ')']
            require(job['head_sha'] == source and job['run_attempt'] == attempt
                    and job['status'] == 'completed' and job['conclusion'] == 'success', 'producer incomplete')
            name = 'sdk-page-background-%s-%d-%d' % (platform, run, attempt)
            artifact, = [a for a in artifacts if a['name'] == name]
            require(artifact['workflow_run']['id'] == run and artifact['workflow_run']['head_sha'] == source
                    and not artifact['expired'] and 0 < artifact['size_in_bytes'] <= 256 * 1024 * 1024
                    and datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc), 'foreign or expired artifact')
            data = download_artifact_zip(artifact['id'])
            require(len(data) == artifact['size_in_bytes']
                    and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'ZIP differs')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate ZIP member')
                def raw(tail):
                    matches = [n for n in archive.namelist() if n == tail or n.endswith('/' + tail)]
                    require(len(matches) == 1, 'missing/duplicate actual file: ' + tail)
                    require(archive.getinfo(matches[0]).file_size <= 128 * 1024 * 1024, 'oversized file')
                    return archive.read(matches[0])
                report = json.loads(raw('background/result.json'))
                require(report['source_sha'] == source and str(report['run_id']) == str(run)
                        and str(report['attempt']) == str(attempt) and report['platform'] == platform
                        and report['accepted'] is True and report['old_api_pixels_identical'] is True,
                        'report identity or result differs')
                require(report['old']['sdk'] == '3.40.0' and report['new']['sdk'] == '3.41.0'
                        and report['old']['abi'] == report['new']['abi'] == 1
                        and report['old']['cases'] == report['new']['cases'] == 12
                        and report['original_native_tests'] > 0, 'original or candidate checks missing')
                for flag in ('complete_product', 'performance_accepted', 'host_ui_accepted', 'six_platform_accepted'):
                    require(report[flag] is False, 'scope falsely broadened')
                old = raw('background/frozen-frames.bin');new = raw('background/candidate-frames.bin')
                require(old and old == new and hashlib.sha256(new).hexdigest() == report['pixel_sha256'], 'raw original API pixels differ')
                suffix = '.exe' if platform == 'windows' else ''
                for kind in ('frozen', 'candidate'):
                    binary = raw(kind + '-consumer/page-background' + suffix)
                    require(hashlib.sha256(binary).hexdigest() == report[kind + '_consumer_sha256'], 'actual consumer differs')
            result['platforms'][platform] = dict(job=job['id'], report=report,
                artifact={k: artifact[k] for k in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        result['accepted'] = True
    except Exception as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    output = Path('build/background-summary');output.mkdir(parents=True, exist_ok=True)
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n');print(json.dumps(result), flush=True)
    require(result['accepted'], 'three-desktop candidate evidence incomplete')


if __name__ == '__main__':
    main()

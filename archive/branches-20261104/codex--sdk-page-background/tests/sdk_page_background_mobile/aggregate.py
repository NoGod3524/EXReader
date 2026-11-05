"""Authenticate all three mobile producers in one Actions source/run/attempt."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'sdk_page_background'))
from aggregate import download_artifact_zip, fetch, pages, require


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions only')
    source = os.environ['GITHUB_SHA'];run = int(os.environ['GITHUB_RUN_ID']);attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    result = dict(source_sha=source, run_id=run, attempt=attempt, accepted=False, platforms={}, problems=[],
                  host_ui_accepted=False, real_device_accepted=False, performance_accepted=False, complete_product=False)
    try:
        metadata = fetch('actions/runs/%d' % run)
        require(metadata['head_sha'] == source and metadata['run_attempt'] == attempt
                and metadata['path'] == '.github/workflows/sdk-page-background-mobile.yml', 'foreign workflow')
        jobs = pages('actions/runs/%d/attempts/%d/jobs' % (run, attempt), 'jobs')
        artifacts = pages('actions/runs/%d/artifacts' % run, 'artifacts')
        for platform in ('android', 'ios-iphone', 'ios-ipad'):
            job, = [j for j in jobs if j['name'] == 'background mobile (' + platform + ')']
            require(job['head_sha'] == source and job['run_attempt'] == attempt
                    and job['status'] == 'completed' and job['conclusion'] == 'success', 'mobile producer failed')
            artifact, = [a for a in artifacts if a['name'] == 'sdk-page-background-mobile-%s-%d-%d' % (platform, run, attempt)]
            require(artifact['workflow_run']['id'] == run and artifact['workflow_run']['head_sha'] == source
                    and not artifact['expired'] and 0 < artifact['size_in_bytes'] <= 256*1024*1024
                    and datetime.fromisoformat(artifact['expires_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc),
                    'expired or foreign artifact')
            data = download_artifact_zip(artifact['id'])
            require(len(data) == artifact['size_in_bytes']
                    and 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest'], 'ZIP mismatch')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                require(len(archive.namelist()) == len(set(archive.namelist())), 'duplicate ZIP member')
                def raw(path):
                    require(path in archive.namelist() and archive.getinfo(path).file_size <= 128*1024*1024,
                            'missing/oversized member: ' + path)
                    return archive.read(path)
                report = json.loads(raw('result.json'))
                require(report['source_sha'] == source and int(report['run_id']) == run
                        and int(report['attempt']) == attempt and report['platform'] == platform
                        and report['accepted'] is True and report['old_api_pixels_identical'] is True, 'identity/result differs')
                require(report['sdk_production_source'] == 'edddc463c06ed5731195cdb8f06b2df6dff7699e'
                        and report['frozen_source'] == '9854061be331fe603a1822d9b2b36ee357154927', 'wrong SDK source')
                for flag in ('native_suite_executed', 'host_ui_accepted', 'performance_accepted', 'real_device_accepted',
                             'complete_product', 'six_platform_accepted'):
                    require(report[flag] is False, 'scope broadened: ' + flag)
                require(report['device']['real_device'] is False, 'simulator misrepresented')
                if platform == 'android':
                    require(report['device']['kind'] == 'emulator' and report['device']['api'] == 34
                            and report['device']['abi'] == 'x86_64', 'wrong Android emulator')
                else:
                    require(report['device']['kind'] == 'simulator' and report['device']['abi'] == 'arm64'
                            and report['device']['family'] == ('iPad' if platform == 'ios-ipad' else 'iPhone'), 'wrong Apple target')
                for kind, version in [('frozen', '3.40.0'), ('candidate', '3.41.0')]:
                    record = json.loads(raw(kind + '.json'))
                    require(record == report['old' if kind == 'frozen' else 'new'] and record['accepted'] is True
                            and record['sdk'] == version and record['abi'] == 1 and record['cases'] == 12
                            and record['checks'] >= (164 if kind == 'frozen' else 535), 'incomplete original probe')
                    digest = hashlib.sha256(raw('programs/' + kind + '/page-background')).hexdigest()
                    require(digest == report[kind + '_consumer_sha256'] == report['device'][kind + '_installed_sha256'],
                            'actual installed executable differs')
                before = raw('frozen-frames.bin');after = raw('candidate-frames.bin')
                require(before and before == after and hashlib.sha256(after).hexdigest() == report['pixel_sha256'],
                        'old API pixels changed')
            result['platforms'][platform] = dict(job=job['id'], report=report,
                artifact={key: artifact[key] for key in ('id', 'name', 'size_in_bytes', 'digest', 'expires_at')})
        result['accepted'] = True
    except Exception as error:
        result['problems'].append(type(error).__name__ + ': ' + str(error))
    output = Path('build/background-mobile-summary');output.mkdir(parents=True, exist_ok=True)
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n');print(json.dumps(result), flush=True)
    require(result['accepted'], 'mobile candidate evidence incomplete')


if __name__ == '__main__':
    main()

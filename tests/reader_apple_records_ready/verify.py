"""Bind original complete strict acceptance to actual same-run readiness commands."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from check_parallel_integration import fetch, download_artifact_zip


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    original = json.loads((ROOT / 'build/apple-reading-summary/summary.json').read_text())
    assert original['accepted'] and (original['source_sha'], original['run_id'], original['attempt']) == (source, run, attempt)
    artifacts = fetch(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
    proofs = []
    for platform in ('macos', 'iphone', 'ipad'):
        rows = [row for row in artifacts if row['name'] == f'apple-reading-ui-{platform}-{run}-{attempt}']
        assert len(rows) == 1
        meta = rows[0]
        assert not meta['expired'] and meta['workflow_run']['head_sha'] == source
        raw = download_artifact_zip(meta['id'])
        assert len(raw) == meta['size_in_bytes'] and 'sha256:' + hashlib.sha256(raw).hexdigest() == meta['digest']
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            assert len(archive.namelist()) == len(set(archive.namelist()))
            preparation = json.loads(archive.read('records-native-preparation.json'))
            assert (preparation['source_sha'], preparation['run_id'], preparation['attempt']) == (source, run, attempt)
            assert preparation['platform'] == platform and preparation['ready'] and preparation['original_tests_not_started']
            assert preparation['production_unmodified']
            if platform != 'macos':
                udid = preparation['destination'][1]
                assert [row['argv'] for row in preparation['commands']] == [
                    ['xcrun', 'simctl', 'boot', udid], ['xcrun', 'simctl', 'bootstatus', udid, '-b']]
                assert all(row.get('exit_code') == 0 for row in preparation['commands'])
                appearance = json.loads(archive.read('appearance-service-preparation.json'))
                assert (appearance['source_sha'], appearance['run_id'], appearance['attempt']) == (source, run, attempt)
                assert appearance['ready'] and appearance['query_only'] and appearance['device'] == udid
                commands = appearance['commands']
                assert len(commands) >= 3 and all(row['timeout_seconds'] <= 180 for row in commands)
                assert commands[0]['argv'] == ['open', '-a', 'Simulator', '--args', '-CurrentDeviceUDID', udid]
                assert commands[1]['argv'] == ['xcrun', 'simctl', 'bootstatus', udid, '-b']
                assert all(row['argv'] == ['xcrun', 'simctl', 'ui', udid, 'appearance'] for row in commands[2:])
                assert commands[-1].get('exit_code') == 0 and commands[-1]['stdout'].strip() in ('light', 'dark')
                preparation['appearance'] = appearance
            proofs.append(dict(platform=platform, artifact_id=meta['id'], preparation=preparation))
    result = dict(accepted=True, source_sha=source, run_id=run, attempt=attempt,
                  fixed_preparation_source='7c457fb68a24d917ac3bd60aa1f961b16fe9ae6b',
                  original_full_strict_passed=True, original_cases_per_platform=7,
                  native_checks=19, sdk_targets=2, readiness=proofs,
                  raw3_ios_accepted=False, physical_device_execution=False, complete_product=False)
    (ROOT / 'build/apple-reading-summary/native-readiness.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'readiness'}), flush=True)


if __name__ == '__main__':
    main()

"""Authenticate the bounded query preparation already hashed by the original raw strict."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    source, run, attempt = (os.environ[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    out = ROOT / 'build/raw3-ios-summary'
    original = json.loads((out / 'summary.json').read_text())
    assert original['accepted'] and (original['source_sha'], original['run_id'], original['attempt']) == (source, run, attempt)
    preparations = []
    for platform in ('iphone', 'ipad'):
        value = json.loads((out / platform / 'appearance-service-preparation.json').read_text())
        assert (value['source_sha'], value['run_id'], value['attempt']) == (source, run, attempt)
        assert value['ready'] and value['query_only']
        result = json.loads((out / platform / 'result.json').read_text())
        udid = result['destination']['udid']
        assert value['device'] == udid
        commands = value['commands']
        assert len(commands) >= 3
        assert commands[0]['argv'] == ['open', '-a', 'Simulator', '--args', '-CurrentDeviceUDID', udid]
        assert commands[1]['argv'] == ['xcrun', 'simctl', 'bootstatus', udid, '-b']
        assert all(row['argv'] == ['xcrun', 'simctl', 'ui', udid, 'appearance'] and row['timeout_seconds'] <= 45 for row in commands[2:])
        assert commands[-1].get('exit_code') == 0 and commands[-1]['stdout'].strip() in ('light', 'dark')
        names = [row['name'] for row in result['commands']]
        assert names.index('erase-isolated-simulator') < names.index('boot-isolated-simulator') < names.index('simulator-ready') < names.index('original-OFF-seven-cases')
        assert 'appearance-service-preparation.json' in result['files']
        preparations.append(dict(platform=platform, preparation=value))
    result = dict(accepted=True, source_sha=source, run_id=run, attempt=attempt,
                  original_full_raw_strict_passed=True, ordinary_merge_source='4749131d722f4f585be767207ed16b32dd9d9b3d',
                  raw_producer_source='72c6bbdd14ebf3be453fa7f0da81119d52675eb5',
                  readiness_source='7c457fb68a24d917ac3bd60aa1f961b16fe9ae6b',
                  original_off_ui_cases_per_platform=7, raw_phases_per_platform=6,
                  readiness=preparations, physical_device_execution=False, complete_product=False,
                  android_interop_accepted=False, full_mobile_sync_accepted=False)
    (out / 'native-readiness.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'readiness'}), flush=True)


if __name__ == '__main__':
    main()

"""Boot an erased original destination, then reuse unchanged bounded query readiness."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/apple_host/page_theme'))
from simulator_ready import prepare_service


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', choices=('macos', 'iphone', 'ipad'), required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination.read_text().splitlines()
    assert len(destination) == 4 and all(destination)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    result = dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  attempt=os.environ['GITHUB_RUN_ATTEMPT'], platform=args.platform,
                  destination=destination, ready=False, commands=[],
                  original_tests_not_started=True, production_unmodified=True)
    path = out / 'records-native-preparation.json'

    def save():
        path.write_text(json.dumps(result, indent=2) + '\n')

    def command(argv, timeout):
        started = time.monotonic()
        row = dict(argv=argv, timeout_seconds=timeout)
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            row.update(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        except subprocess.TimeoutExpired:
            row.update(exit_code=None, timed_out=True)
        row['elapsed_seconds'] = time.monotonic() - started
        result['commands'].append(row)
        save()
        print('RECORDS-NATIVE-PREPARATION', json.dumps(row), flush=True)
        assert row.get('exit_code') == 0, 'native pre-test device boot failed'

    save()
    if args.platform == 'macos':
        assert destination[0] == 'platform=macOS'
        result['mode'] = 'actual-macos-no-simulator-preparation'
    else:
        udid = destination[1]
        assert destination[0] == 'platform=iOS Simulator,id=' + udid
        command(['xcrun', 'simctl', 'boot', udid], 180)
        command(['xcrun', 'simctl', 'bootstatus', udid, '-b'], 180)
        prepare_service(udid, out)
        proof = json.loads((out / 'appearance-service-preparation.json').read_text())
        assert proof['ready'] and proof['query_only'] and proof['device'] == udid
        result['mode'] = 'explicit-post-erase-boot-plus-original-query-only-readiness'
    result['ready'] = True
    save()
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()

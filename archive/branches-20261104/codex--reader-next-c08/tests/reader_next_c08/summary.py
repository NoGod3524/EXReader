"""Join the static and emulator jobs: one source, one run/attempt, one APK, one result."""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import common


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--static', type=pathlib.Path, required=True)
    parser.add_argument('--emulator', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('build/c08-summary'))
    args = parser.parse_args()
    problems = []
    try:
        selftest = common.read_json(args.static / 'validate-selftest.json')
        auth_static = common.read_json(args.static / 'authenticate/attestation.json')
        emulator = common.read_json(args.emulator / 'emulator-report.json')
        auth_emulator = common.read_json(args.emulator / 'authenticate/attestation.json')
    except Exception as error:
        problems.append('missing job evidence: %s' % error)
        selftest = auth_static = emulator = auth_emulator = {}
    if selftest and not all(selftest.values()):
        problems.append('validator self-test has a failing case: %r' % selftest)
    if auth_static and auth_emulator:
        for key in ('source_sha', 'run_id', 'attempt'):
            if auth_static['identity'].get(key) != auth_emulator['identity'].get(key):
                problems.append('static and emulator jobs differ in ' + key)
        if [row['digest'] for row in auth_static['artifacts']] != [row['digest'] for row in auth_emulator['artifacts']]:
            problems.append('static and emulator authenticated different producer artifacts')
    if emulator:
        if emulator['identity'] != auth_emulator['identity']:
            problems.append('emulator report and its authentication disagree on identity')
        if not emulator.get('accepted') or emulator.get('mandatory_failed'):
            problems.append('emulator readback not accepted: %r' % emulator.get('failure'))
    accepted = not problems
    result = {'identity': auth_static.get('identity') if auth_static else None, 'accepted': accepted,
              'problems': problems, 'emulator_checks': (emulator or {}).get('checks_total'),
              'emulator_passed': (emulator or {}).get('checks_passed'),
              'apk': (emulator or {}).get('apk'),
              'scope': 'readback of original/books/progress/notes via the shipped public C ABI; '
                       'API34 default x86_64 emulator; not a device, store, signing or performance claim'}
    common.write_json(args.output / 'summary.json', result)
    print(result)
    if not accepted:
        sys.exit(1)


if __name__ == '__main__':
    main()

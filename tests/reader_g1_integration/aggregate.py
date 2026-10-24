"""Preserve G08's strict checks; additionally authenticate new suites in the same ZIPs."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import zipfile

BASE = Path(__file__).resolve().parents[1] / 'reader_module_composition'
spec = importlib.util.spec_from_file_location('original_composition_gate', BASE / 'check_artifacts.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
# Only the caller identity changes. All original positive and rejection checks
# and their mandatory platform/job/artifact identity checks remain intact.
original.WORKFLOW = '.github/workflows/reader-g1-integration.yml'
REQUIRED = ['new-five-module-chain-and-sdk-free-product-link',
            'G02-thumbnails-original-regression-allocation', 'G03-reading-commands',
            'G04-annotation-view', 'G05-annotation-export', 'G06-local-downloads-and-old-build-control']


def validate(report, phase, source, run, attempt):
    assert report.get('accepted') is True and report.get('complete_product') is False
    assert report.get('source_sha') == source and str(report.get('run_id')) == str(run)
    assert str(report.get('attempt')) == str(attempt) and report.get('phase') == phase
    rows = report.get('checks', [])
    expected = REQUIRED if phase == 'initial' else REQUIRED[:1]
    assert [row['name'] for row in rows] == expected and all(row.get('pass') is True for row in rows)
    assert report.get('consumers'), 'consumer hashes absent'


def self_test():
    import copy
    original.self_test()
    good = dict(accepted=True, complete_product=False, source_sha='s', run_id=1, attempt=2,
                phase='initial', checks=[{'name': name, 'pass': True} for name in REQUIRED], consumers={'c': 'hash'})
    validate(good, 'initial', 's', 1, 2)
    controls = [lambda x: x['checks'].pop(), lambda x: x['checks'][0].update({'pass': False}),
                lambda x: x.update(source_sha='other'), lambda x: x.update(attempt=9),
                lambda x: x.update(phase='relocated'), lambda x: x.update(consumers={})]
    for mutation in controls:
        bad = copy.deepcopy(good)
        mutation(bad)
        try:
            validate(bad, 'initial', 's', 1, 2)
        except AssertionError:
            continue
        raise AssertionError('new gate accepted a negative control')
    print('extended aggregate: 6 additional rejection controls passed')


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    if '--self-test' in sys.argv:
        self_test()
        return 0
    # Authenticates bytes/digests/expiry and three successful producers, writes
    # authenticated ZIPs, and executes original verify_bundles without changes.
    if original.main() != 0:
        return 1
    downloads = Path(sys.argv[sys.argv.index('--downloads') + 1])
    output = Path(sys.argv[sys.argv.index('--output') + 1])
    summary_path = output / 'result.json'
    summary = json.loads(summary_path.read_text())
    try:
        for key, _ in original.PLATFORMS:
            name = 'reader-module-composition-%s-%s-%s.zip' % (
                key, os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'])
            with zipfile.ZipFile(downloads / name) as archive:
                for phase in ('initial', 'relocated'):
                    tail = 'g1/' + phase + '/result.json'
                    matches = [p for p in archive.namelist() if p == tail or p.endswith('/' + tail)]
                    assert len(matches) == 1, 'missing/duplicate extended report ' + tail
                    report_path = matches[0]
                    report = json.loads(archive.read(report_path))
                    validate(report, phase, os.environ['GITHUB_SHA'], os.environ['GITHUB_RUN_ID'],
                             os.environ['GITHUB_RUN_ATTEMPT'])
                    root = report_path[:-len('result.json')]
                    for file, digest in report['consumers'].items():
                        assert '/' not in file and '\\' not in file
                        assert hashlib.sha256(archive.read(root + file)).hexdigest() == digest
                    codec = json.loads(archive.read(root + 'codec/result.json'))
                    assert codec['accepted'] is True and codec['sdk_symbols'] is False
                    assert codec['source_sha'] == os.environ['GITHUB_SHA']
                    assert str(codec['run_id']) == os.environ['GITHUB_RUN_ID']
                    assert str(codec['attempt']) == os.environ['GITHUB_RUN_ATTEMPT']
                    assert len(codec['sqlite_providers']) == 1
                    summary['platforms'][key]['g1_' + phase] = report
        summary['scope'] = 'three-desktop 18-package composition, G02-G06 original judges and SDK-free product codecs'
        summary['accepted'] = True
    except Exception as error:
        summary['accepted'] = False
        summary['problems'].append(str(error))
    summary_path.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))
    return 0 if summary['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

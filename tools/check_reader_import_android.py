#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Strict same-run real-SDK/catalog adapter and killed-process recovery evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from check_reader_catalog_android import inspect as inspect_catalog

TESTS = {
    'hashesStoredOriginalInChunks', 'registersAtomicallyAndIdempotently',
    'preservesDuplicateMetadataAndHistory', 'keepsLegacyAndBoundedEpubModes',
    'rejectsWrongCopyHashAndLength', 'rejectsInvalidatedSourceReads',
    'repairsSdkCommitBeforeCatalog', 'rollsBackSqlFailureAndRepairsOnReopen',
    'cancelsBeforePublicationWithoutDeletingDuplicate', 'retainsPublishedBookOnCatalogFailure',
    'clearsLocalMappingBeforeSdkDelete', 'rejectsConflictingLocalIdentity',
    'keepsOldestHistoricalDuplicateAndActualMode', 'normalizesSortTitleWithoutChangingDisplayTitle',
}


def inspect(root):
    result, inventory = [], []
    for path in sorted((root / 'mapping-reports').rglob('*.xml')):
        raw = path.read_bytes()
        xml = ET.fromstring(raw)
        for suite in xml.iter('testsuite'):
            if any(int(suite.get(status, '0')) for status in ('failures', 'errors', 'skipped')):
                raise ValueError('mapping suite failed or skipped')
        for case in xml.iter('testcase'):
            if case.get('classname') != 'org.exreader.host.ImportMappingTest' or any(
                    case.find(status) is not None for status in ('failure', 'error', 'skipped')):
                raise ValueError('unexpected, failed or skipped mapping case')
            result.append(case.get('name'))
        inventory.append({'path': path.relative_to(root).as_posix(), 'bytes': len(raw),
                          'sha256': hashlib.sha256(raw).hexdigest()})
    if len(result) != len(TESTS) or set(result) != TESTS:
        raise ValueError('mapping cases missing, duplicated or unexpected')
    phases = []
    for kind in ('before', 'during'):
        seed = root / ('seed-' + kind + '.txt')
        recovery = root / ('recover-' + kind + '.txt')
        seed_text = seed.read_text()
        text = recovery.read_text()
        if 'INSTRUMENTATION_RESULT: shortMsg=Process crashed.' not in seed_text:
            raise ValueError('seed process was not actually killed: ' + kind)
        if 'EXR_MAPPING_RECOVERED recover-' + kind not in text or not re.search(
                r'^INSTRUMENTATION_CODE: -1\s*$', text, re.M) or 'EXR_MAPPING_PHASE_FAILED' in text:
            raise ValueError('killed-process recovery did not pass: ' + kind)
        phases.append({'phase': kind, 'seed_sha256': hashlib.sha256(seed.read_bytes()).hexdigest(),
                       'recovery_sha256': hashlib.sha256(recovery.read_bytes()).hexdigest()})
    return {'tests': sorted(result), 'reports': inventory, 'killed_process_recovery': phases,
            'catalog': inspect_catalog(root / 'catalog-reports')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence
    output = {'accepted': False, 'problems': [], 'scope': 'Android recoverable product import mapping',
              'source_sha': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'physical_device_execution': False}
    try:
        if os.environ.get('GITHUB_ACTIONS') != 'true' or not output['source_sha']:
            raise ValueError('only GitHub Actions can grant acceptance')
        if (root / 'source.txt').read_text().strip() != output['source_sha']:
            raise ValueError('workflow and checkout source differ')
        if (root / 'device-api.txt').read_text().strip() != '34' or (
                root / 'device-abi.txt').read_text().strip() != 'x86_64':
            raise ValueError('unexpected device identity')
        output.update(inspect(root))
        apks = {}
        for name in ('app-debug.apk', 'app-debug-androidTest.apk'):
            raw = (root / 'apks' / name).read_bytes()
            if not raw:
                raise ValueError('empty application/instrumentation APK')
            apks[name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        output['apks'] = apks
        output.update(accepted=True, passed=len(TESTS), failed=0, skipped=0, catalog_passed=8,
                      process_recovery_passed=2)
    except (ValueError, OSError, ET.ParseError) as error:
        output['problems'].append(str(error))
    root.mkdir(parents=True, exist_ok=True)
    (root / 'result.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output))
    if not output['accepted']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

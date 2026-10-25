#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Merge the four S02 evidence documents into one accepted/blocked summary.

Every stage document is optional at read time: a stage that produced nothing
becomes a named failed check instead of aborting the merge, so a blocked run
still leaves a complete, quotable summary behind.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import common


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--smoke', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    def load(stage, path):
        try:
            return common.read_json(path)
        except Exception as error:
            return {'checks': [{'id': 'stage_%s_missing' % stage, 'status': 'fail',
                                'detail': type(error).__name__ + ': ' + str(error)}],
                    'problems': ['stage %s produced no document' % stage]}

    documents = {'producer': load('producer', args.producer),
                 'package': load('package', args.package),
                 'audit': load('audit', args.audit),
                 'smoke': load('smoke', args.smoke)}
    checks = common.Checks()

    for stage, document in documents.items():
        for row in document.get('checks') or []:
            record = dict(row)
            record['stage'] = stage
            checks.items.append(record)
            print(json.dumps({'stage': stage, 'check': row.get('id'),
                              'status': row.get('status')}, ensure_ascii=False), flush=True)
        print(json.dumps({'stage': stage, 'checks': len(document.get('checks') or []),
                          'problems': len(document.get('problems') or []),
                          'ok': document.get('ok')}, ensure_ascii=False), flush=True)
    checks.add('all_stages_reported',
               all(document.get('checks') for document in documents.values()),
               ' '.join('%s=%d' % (stage, len(documents[stage].get('checks') or []))
                        for stage in ('producer', 'package', 'audit', 'smoke')))
    for stage, document in documents.items():
        checks.add('no_problems_' + stage, not document.get('problems'),
                   json.dumps(document.get('problems') or []))

    expected = os.environ.get('GITHUB_SHA', '')
    checks.add('single_verifier_source',
               bool(expected) and all(document.get('verifier_source') == expected
                                      for document in documents.values()),
               'workflow %s, documents %s' % (expected, [document.get('verifier_source')
                                                         for document in documents.values()]))
    producer = documents['producer']
    package = documents['package']
    audit = documents['audit']
    smoke = documents['smoke']
    producer_run = producer.get('run') or {}
    artifact = producer.get('selected_artifact') or {}
    program = (producer.get('program') or {}).get('sha256')
    identity = (package.get('identity') or {}).get('producer') or {}
    checks.add('single_program_identity',
               bool(program)
               and bool((package.get('archive') or {}).get('name'))
               and (package.get('relocated') or {}).get('program_sha256') == program
               and smoke.get('program_sha256') == program
               and any(row.get('id') == 'program_digest' and row.get('status') == 'pass'
                       for row in audit.get('checks') or []),
               'producer program %s' % program)
    checks.add('single_producer_run',
               identity.get('run') == producer_run.get('id')
               and identity.get('attempt') == producer_run.get('attempt')
               and identity.get('source') == producer_run.get('head_sha')
               and identity.get('artifact_digest') == artifact.get('digest'),
               'run %s attempt %s source %s' % (producer_run.get('id'),
                                                producer_run.get('attempt'),
                                                producer_run.get('head_sha')))

    document = {
        'schema': 1,
        'kind': 's02-verification-summary',
        'verifier_source': expected,
        'accepted': checks.accepted(),
        'producer': {'repository': producer.get('repository'), 'run': producer_run,
                     'artifact': artifact, 'zip': producer.get('zip'),
                     'program': producer.get('program'),
                     'payload': (producer.get('payload') or {}).get('totals'),
                     'pinned': producer.get('pinned'),
                     'build': (producer.get('build') or {})},
        'candidate': {'archive': package.get('archive'),
                      'relocated': package.get('relocated'), 'identity': package.get('identity')},
        'dependencies': audit.get('dependencies'),
        'resources': audit.get('resources'),
        'desktop_entry': audit.get('desktop_entry'),
        'checks': checks.items,
        'counts': {'total': len(checks.items),
                   'passed': len([row for row in checks.items if row.get('status') == 'pass']),
                   'failed': len(checks.failed()),
                   'observed': len(checks.observed()),
                   'by_stage': {stage: len(documents[stage].get('checks') or [])
                                for stage in documents}},
        'problems': checks.failed(),
        'recorded_findings': [{'id': row.get('id'), 'detail': row.get('detail'),
                               'stage': row.get('stage')}
                              for row in checks.items if row.get('status') == 'observed'],
        'scope': {
            'granted': ['Linux x86_64 Ubuntu 22.04 runner: relocatable candidate seal/extract, '
                        'dynamic section and loader resolution, fonts/resources, generated '
                        'desktop entry launch, XDG user data placement, GTK/AT-SPI default-launch '
                        'smoke and original-book read-back on the relocated package'],
            'not_granted': ['other Linux distributions or architectures', 'Wayland session',
                            'physical device or screen reader', 'performance budget',
                            'system-wide installation or package manager integration',
                            'icon theme integration (the producer payload ships no icon)',
                            'Windows, macOS, Android or Apple hosts',
                            'host source changes (root owns common-source integration)'],
        },
        'not_tested': [
            'distributions other than the Ubuntu 22.04 GitHub runner image',
            'a real desktop session, hardware compositor or screen reader',
            'performance and memory budgets',
            'the producer payload desktop icon/theme integration (absent from producer)',
        ],
    }
    common.write_json(args.output, document)
    print(json.dumps({'recorded_findings': document['recorded_findings']}, ensure_ascii=False))
    print(json.dumps({'accepted': document['accepted'], 'checks': document['counts'],
                      'failed': document['problems'][:8]}))
    return 0 if document['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())

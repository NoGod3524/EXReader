#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Merge the four S02 evidence documents into one accepted/blocked summary."""
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
    documents = {'producer': common.read_json(args.producer),
                 'package': common.read_json(args.package),
                 'audit': common.read_json(args.audit),
                 'smoke': common.read_json(args.smoke)}
    checks = common.Checks()

    for stage, document in documents.items():
        for row in document.get('checks') or []:
            record = dict(row)
            record['stage'] = stage
            checks.items.append(record)
            print(json.dumps({'stage': stage, 'check': row['id'], 'status': row['status']},
                             ensure_ascii=False), flush=True)
    checks.add('all_stages_reported',
               all(document.get('checks') for document in documents.values()),
               'producer=%d package=%d audit=%d smoke=%d' % tuple(
                   len(documents[stage].get('checks') or [])
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
    program = producer.get('program', {}).get('sha256')
    checks.add('single_program_identity',
               bool(program)
               and package['archive'].get('name')
               and package['relocated'].get('program_sha256') == program
               and audit.get('relocated')
               and smoke.get('program_sha256') == program,
               'producer program %s' % program)
    identity = package.get('identity') or {}
    checks.add('single_producer_run',
               identity.get('producer', {}).get('run') == producer['run']['id']
               and identity.get('producer', {}).get('attempt') == producer['run']['attempt']
               and identity.get('producer', {}).get('source') == producer['run']['head_sha']
               and identity.get('producer', {}).get('artifact_digest')
               == producer['selected_artifact'].get('digest'),
               'run %s attempt %s source %s' % (producer['run']['id'],
                                                producer['run']['attempt'],
                                                producer['run']['head_sha']))

    document = {
        'schema': 1,
        'kind': 's02-verification-summary',
        'verifier_source': expected,
        'accepted': checks.accepted(),
        'producer': {'repository': producer.get('repository'),
                     'run': producer['run'], 'artifact': producer['selected_artifact'],
                     'zip': producer['zip'], 'program': producer['program'],
                     'payload': producer['payload']['totals'],
                     'pinned': producer.get('pinned')},
        'candidate': {'archive': package.get('archive'), 'relocated': package.get('relocated'),
                      'identity': package.get('identity')},
        'dependencies': audit.get('dependencies'),
        'resources': audit.get('resources'),
        'desktop_entry': audit.get('desktop_entry'),
        'checks': checks.items,
        'counts': {'total': len(checks.items),
                   'passed': len([row for row in checks.items if row['status'] == 'pass']),
                   'failed': len(checks.failed()),
                   'by_stage': {stage: len(documents[stage].get('checks') or [])
                                for stage in documents}},
        'problems': checks.failed(),
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
    print(json.dumps({'accepted': document['accepted'], 'checks': document['counts'],
                      'failed': document['problems'][:8]}))
    return 0 if document['accepted'] else 1


if __name__ == '__main__':
    sys.exit(main())

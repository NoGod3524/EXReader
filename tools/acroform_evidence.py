#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reconcile the per-platform AcroForm artifacts into committed evidence.

Runs inside the workflow after every platform job.  It refuses to write the
evidence when the cross-platform corpus identity differs, when any platform
reports a failing, missing, skipped or duplicated file, or when an installed
consumer report is absent.  Raw qpdf transcripts are trimmed here: the full
logs stay in the workflow run, the committed record keeps the tool identity,
the per-file verdicts and the counts.
"""

import argparse
import hashlib
import json
import pathlib
import sys

CORPUS_SCHEMA = 'exreader-acroform-corpus-manifest/1'
EVIDENCE_SCHEMA = 'exreader-acroform-corpus-evidence/1'


def find(root, name):
    matches = sorted(root.rglob(name))
    return matches[0] if matches else None


def find_all(root, name):
    return sorted(root.rglob(name))


def load(path):
    if path is None:
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def trim_reference(report):
    if not report:
        return None
    files = []
    for record in report.get('files', []):
        files.append({
            'id': record.get('id'), 'base': record.get('base'),
            'checks': record.get('checks', []),
            'problems': record.get('problems', []),
            'qpdf': {key: record.get('qpdf', {}).get(key)
                     for key in ('exit', 'errors', 'warnings', 'passed', 'available')},
            'qpdf_output': {key: record.get('qpdf_output', {}).get(key)
                            for key in ('exit', 'errors', 'warnings', 'passed', 'available')},
            'render': record.get('render'),
            'ink': record.get('ink'),
            'input_bytes': record.get('input_bytes'),
            'output_bytes': record.get('output_bytes'),
        })
    return {
        'schema': report.get('schema'), 'mode': report.get('mode'),
        'tools': report.get('tools'), 'resolution_dpi': report.get('resolution_dpi'),
        'ink_level': report.get('ink_level'), 'inset_points': report.get('inset_points'),
        'summary': report.get('summary'), 'failure_count': len(report.get('failures', [])),
        'failures': report.get('failures', [])[:50], 'files': files,
    }


def main():
    parser = argparse.ArgumentParser(description='Reconcile AcroForm corpus artifacts')
    parser.add_argument('--artifacts', required=True, type=pathlib.Path)
    parser.add_argument('--out', required=True, type=pathlib.Path)
    parser.add_argument('--source', default='unknown')
    arguments = parser.parse_args()
    root = arguments.artifacts
    problems = []
    platforms = {}
    corpus_manifests = {}
    evidence_manifests = {}
    references = {}
    consumers = {}

    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        label = directory.name.replace('EXReader-acroform-', '')
        platforms[label] = directory
        corpus = None
        for candidate in find_all(directory, 'manifest.json'):
            data = load(candidate)
            if not data:
                continue
            if data.get('schema') == CORPUS_SCHEMA:
                corpus = data
            elif data.get('schema') == EVIDENCE_SCHEMA:
                evidence_manifests[label] = data
        if corpus is not None:
            corpus_manifests[label] = corpus
        for name in ('reference-inputs.json', 'reference-outputs.json'):
            found = find(directory, name)
            if found is None:
                continue
            report = load(found)
            references['%s/%s' % (label, name)] = trim_reference(report)
            if report.get('failures'):
                problems.append('%s: reference %s reported %d problems' %
                                (label, name, len(report['failures'])))
        consumer = load(find(directory, 'installed-form.json'))
        if consumer is not None:
            consumers[label] = consumer

    if 'corpus' not in corpus_manifests:
        problems.append('the corpus artifact carries no corpus manifest')
    reference_files = None
    for label, manifest in corpus_manifests.items():
        if manifest.get('file_count', 0) < 30:
            problems.append('%s: corpus holds %d files below the gate' % (label, manifest.get('file_count', 0)))
        if reference_files is None:
            reference_files = [(entry['id'], entry['base'], entry['size'], entry['sha256'])
                               for entry in manifest.get('files', [])]
        else:
            current = [(entry['id'], entry['base'], entry['size'], entry['sha256'])
                       for entry in manifest.get('files', [])]
            if current != reference_files:
                problems.append('%s: corpus identity differs from the corpus job' % label)

    for label in ('Linux', 'Windows'):
        evidence = evidence_manifests.get(label)
        if evidence is None:
            problems.append('%s: no evidence manifest was produced' % label)
            continue
        counts = evidence.get('counts', {})
        if counts.get('failed'):
            problems.append('%s: %d files failed acceptance' % (label, counts['failed']))
        for field_name in ('missing', 'skipped', 'duplicate_content'):
            if counts.get(field_name):
                problems.append('%s: %s=%d' % (label, field_name, counts[field_name]))
        if counts.get('files', 0) < 30:
            problems.append('%s: %d files measured' % (label, counts.get('files', 0)))
        if not counts.get('assertions'):
            problems.append('%s: no assertions were recorded' % label)
        if not counts.get('harness_checks'):
            problems.append('%s: the C harness reported no CHECK executions' % label)
        consumer = consumers.get(label)
        if consumer is None:
            problems.append('%s: no installed consumer report' % label)
        else:
            if consumer.get('failed'):
                problems.append('%s: installed consumer reported %d failures' % (label, consumer['failed']))
            if consumer.get('covered', 0) < 20:
                problems.append('%s: installed consumer covered only %d documents' % (label, consumer.get('covered', 0)))

    sanitizer = evidence_manifests.get('sanitizer')
    if sanitizer is None:
        problems.append('sanitizer: no evidence manifest was produced')
    elif sanitizer.get('counts', {}).get('failed'):
        problems.append('sanitizer: %d acceptance failures' % sanitizer['counts']['failed'])
    else:
        consumer_free = sanitizer.get('counts', {})
        if not consumer_free.get('harness_checks'):
            problems.append('sanitizer: the harness reported no CHECK executions')

    if not references:
        problems.append('no independent reference report was uploaded')

    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)
    files_dir = out / 'files'
    files_dir.mkdir(parents=True, exist_ok=True)
    linux = evidence_manifests.get('Linux')
    if linux is not None:
        for record in linux.get('files', []):
            (files_dir / ('%s.json' % record['id'])).write_text(
                json.dumps(record, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for label in ('Linux', 'Windows', 'sanitizer'):
        evidence = evidence_manifests.get(label)
        if evidence is not None:
            (out / ('manifest-%s.json' % label.lower())).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for name, report in references.items():
        label = name.split('/')[0]
        kind = 'inputs' if 'inputs' in name else 'outputs'
        (out / ('reference-%s-%s.json' % (label.lower(), kind))).write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    identity = {
        'schema': 'exreader-acroform-corpus-identity/1',
        'source_sha': arguments.source,
        'corpus_files': len(reference_files or []),
        'corpus_sha256': {entry[1]: entry[3] for entry in (reference_files or [])},
        'platforms': sorted(platforms.keys()),
        'evidence': {label: manifest.get('counts') for label, manifest in evidence_manifests.items()},
        'consumers': consumers,
        'reference_tools': {label: report.get('tools')
                            for label, report in [('inputs', references.get('corpus/reference-inputs.json'))]},
        'problems': problems,
    }
    (out / 'identity.json').write_text(json.dumps(identity, ensure_ascii=False, indent=1) + '\n',
                                       encoding='utf-8')
    lines = ['# WP9 AcroForm independent document corpus', '',
             'Source: %s' % arguments.source, '',
             '| platform | files | passed | failed | skipped | assertions | harness |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for label in ('Linux', 'Windows', 'sanitizer'):
        counts = evidence_manifests.get(label, {}).get('counts', {})
        lines.append('| %s | %d | %d | %d | %d | %d | %d |' % (
            label, counts.get('files', 0), counts.get('passed', 0), counts.get('failed', 0),
            counts.get('skipped', 0), counts.get('assertions', 0), counts.get('harness_checks', 0)))
    lines.extend(['', 'Installed consumer: %s' %
                  ', '.join('%s covered %d skipped %d failed %d' % (
                      label, report.get('covered', 0), report.get('skipped', 0), report.get('failed', 0))
                      for label, report in sorted(consumers.items())), ''])
    if problems:
        lines.append('## Reconciliation failures')
        lines.extend('- %s' % problem for problem in problems)
    else:
        lines.append('All platforms agree on the frozen corpus identity and every '
                     'independent document passed its acceptance rules.')
    (out / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'platforms': sorted(platforms), 'problems': problems}, indent=1))
    for problem in problems:
        print('FAIL ' + problem, file=sys.stderr)
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())

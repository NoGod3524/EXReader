#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Turn raw AcroForm corpus measurements into per-file JSON and a manifest.

The C driver only reports what happened; this checker owns the verdicts.  It
compares every measurement against the frozen spec, applies the acceptance
rules for accepted, rejected, cancelled and unreadable documents, folds in the
independent reference results, and refuses to publish a summary when a file is
missing, duplicated, skipped or still differs from its expectation.

The summary separates the three counts that must never be conflated:
  files      - independent PDF documents
  assertions - expected facts compared by this checker
  harness    - CHECK executions inside the C driver
"""

import argparse
import hashlib
import json
import pathlib
import sys

EXPECTED_KINDS = ('text', 'checkbox', 'radio', 'choice', 'pushbutton', 'signature', 'unknown')


def decode_hex(value):
    if value == '-':
        return None
    return bytes.fromhex(value)


def decode_text(value):
    raw = decode_hex(value)
    if raw is None:
        return None
    return raw.decode('utf-8', 'surrogateescape')


def decode_list(value):
    if value == '-':
        return []
    return [decode_text(item) for item in value.split(',')]


def decode_options(value):
    if value == '-':
        return []
    out = []
    for item in value.split(','):
        left, right = item.split(':', 1)
        out.append({'value': decode_text(left), 'label': decode_text(right)})
    return out


def decode_widgets(value):
    if value == '-':
        return []
    out = []
    for item in value.split(';'):
        cells = item.split(',')
        page = int(cells[0])
        rect = [int(number) / 1000.0 for number in cells[1:5]]
        on_state = decode_text(cells[5])
        out.append({'page': None if page < 0 else page, 'rect': rect, 'on_state': on_state})
    return out


class Measurements:
    def __init__(self):
        self.meta = {}
        self.file = None
        self.reads = {}
        self.fields = {'in': [], 'out': []}
        self.need = {}
        self.annots = {'in': [], 'out': []}
        self.write = None
        self.repeat = None
        self.reopen = None
        self.ink = []


def parse_results(path):
    measurements = {}
    order = []
    for line in pathlib.Path(path).read_text(encoding='utf-8').splitlines():
        if not line:
            continue
        cells = line.split('	')
        tag = cells[0]
        if tag == 'META':
            continue
        index = int(cells[1])
        if index not in measurements:
            measurements[index] = Measurements()
            order.append(index)
        item = measurements[index]
        if tag == 'F':
            item.file = {'id': cells[2], 'base': decode_text(cells[3]),
                         'size': int(cells[4]), 'fnv': cells[5]}
        elif tag == 'R':
            item.reads[cells[2]] = {'status': cells[3], 'code': int(cells[4]),
                                    'fields': int(cells[5])}
        elif tag == 'FLD':
            item.fields[cells[2]].append({
                'name': decode_text(cells[3]),
                'kind': cells[4],
                'flags': int(cells[5]),
                'issues': int(cells[6]),
                'max_length': int(cells[7]),
                'values': decode_list(cells[8]),
                'defaults': decode_list(cells[9]),
                'options': decode_options(cells[10]),
                'widgets': decode_widgets(cells[11]),
            })
        elif tag == 'S':
            item.need[cells[2]] = {'present': cells[3] == '1', 'value': cells[4] == '1'}
        elif tag == 'A':
            item.annots[cells[2]].append({
                'page': int(cells[3]),
                'rect': [int(cells[4 + offset]) / 1000.0 for offset in range(4)],
                'state': decode_text(cells[8]),
                'kind': cells[9],
                'length': int(cells[10]),
                'hash': cells[11],
                'states': [] if cells[12] == '-' else [decode_text(part) for part in cells[12].split(',')],
            })
        elif tag == 'W':
            item.write = {'op': cells[2], 'status': cells[3], 'code': int(cells[4]),
                          'size': int(cells[5]), 'prefix': cells[6] == '1',
                          'same': cells[7] == '1', 'changes': int(cells[8]),
                          'name': decode_text(cells[9]), 'message': decode_text(cells[10])}
        elif tag == 'J':
            item.repeat = {'first': cells[2], 'first_code': int(cells[3]),
                           'second': cells[4], 'second_code': int(cells[5]),
                           'noop': cells[6], 'noop_code': int(cells[7]),
                           'noop_size': int(cells[8]), 'noop_same': cells[9] == '1'}
        elif tag == 'RO':
            item.reopen = {'status': cells[2], 'code': int(cells[3]), 'fields': int(cells[4])}
        elif tag == 'INK':
            item.ink.append({'field': decode_text(cells[3]), 'widget': int(cells[4]),
                             'page': int(cells[5]), 'dark': int(cells[6]),
                             'message': decode_text(cells[7]) if len(cells) > 7 else None})
    meta = {}
    for line in pathlib.Path(path).read_text(encoding='utf-8').splitlines():
        if line.startswith('META\t'):
            _, key, value = line.split('\t', 2)
            meta[key] = value
    return measurements, order, meta


def option_values(field):
    return [option['value'] for option in field['options']]


def expected_after(entry):
    """Values the reopened document must report for each changed field."""
    out = {}
    indices = {}
    for change in entry['changes']:
        field = next((item for item in entry['fields'] if item['name'] == change['field']), None)
        values = [value['hex'] if isinstance(value, dict) else value for value in change['values']]
        if field is None:
            continue
        if field['kind'] in ('checkbox', 'radio'):
            out[change['field']] = [values[0]] if values else []
        elif field['kind'] == 'choice':
            names = option_values(field)
            if field['flags'] & (1 << 21):
                ordered = [name for name in names if name in values]
                out[change['field']] = ordered
                indices[change['field']] = [names.index(name) for name in ordered]
            else:
                out[change['field']] = values[:1]
                indices[change['field']] = [names.index(values[0])] if values and values[0] in names else []
        else:
            out[change['field']] = values[:1] if values else ['']
    return out, indices


class Verdict:
    def __init__(self):
        self.assertions = 0
        self.failures = []

    def check(self, condition, message):
        self.assertions += 1
        if not condition:
            self.failures.append(message)
        return condition


def annot_for_widget(annots, widget):
    for annot in annots:
        if annot['page'] != widget['page']:
            continue
        if any(abs(annot['rect'][index] - widget['rect'][index]) > 0.01 for index in range(4)):
            continue
        return annot
    return None


def annot_match(widgets, annot):
    for widget in widgets:
        if annot['page'] != widget['page']:
            continue
        if all(abs(annot['rect'][index] - widget['rect'][index]) <= 0.01 for index in range(4)):
            return widget
    return None


def same_widgets(expected, actual):
    if len(expected) != len(actual):
        return False
    for left, right in zip(expected, actual):
        if left['page'] != right['page']:
            return False
        if any(abs(left['rect'][index] - right['rect'][index]) > 0.01 for index in range(4)):
            return False
        if left['on_state'] != right['on_state']:
            return False
    return True


def compare_field_list(verdict, expected, actual, label):
    verdict.check(len(expected) == len(actual),
                  '%s: field count %d != expected %d' % (label, len(actual), len(expected)))
    for want, got in zip(expected, actual):
        name = want['name']
        verdict.check(got['name'] == name, '%s: name %r != %r' % (label, got['name'], name))
        if got['name'] != name:
            continue
        verdict.check(got['kind'] == want['kind'],
                      '%s %s: kind %r != %r' % (label, name, got['kind'], want['kind']))
        verdict.check(got['flags'] == want['flags'],
                      '%s %s: flags %d != %d' % (label, name, got['flags'], want['flags']))
        verdict.check(got['issues'] == want['issues'],
                      '%s %s: issues %d != %d' % (label, name, got['issues'], want['issues']))
        verdict.check(got['max_length'] == want['max_length'],
                      '%s %s: MaxLen %d != %d' % (label, name, got['max_length'], want['max_length']))
        verdict.check(got['values'] == want['values'],
                      '%s %s: values %r != %r' % (label, name, got['values'], want['values']))
        verdict.check(got['defaults'] == want['defaults'],
                      '%s %s: defaults %r != %r' % (label, name, got['defaults'], want['defaults']))
        verdict.check(got['options'] == want['options'],
                      '%s %s: options %r != %r' % (label, name, got['options'], want['options']))
        verdict.check(same_widgets(want['widgets'], got['widgets']),
                      '%s %s: widgets %r != %r' % (label, name, got['widgets'], want['widgets']))


def main():
    parser = argparse.ArgumentParser(description='Verify the AcroForm corpus measurements')
    parser.add_argument('--corpus', required=True, type=pathlib.Path)
    parser.add_argument('--edited', required=True, type=pathlib.Path)
    parser.add_argument('--results', required=True, type=pathlib.Path)
    parser.add_argument('--out', required=True, type=pathlib.Path)
    parser.add_argument('--platform', default='unknown')
    parser.add_argument('--reference', type=pathlib.Path)
    parser.add_argument('--require-reference', action='store_true')
    arguments = parser.parse_args()

    spec = json.loads((arguments.corpus / 'corpus-spec.json').read_text(encoding='utf-8'))
    measurements, order, meta = parse_results(arguments.results)
    reference = None
    reference_files = {}
    if arguments.reference and arguments.reference.exists():
        reference = json.loads(arguments.reference.read_text(encoding='utf-8'))
        for record in reference.get('files', []):
            reference_files[record['id']] = record

    spec_by_id = {entry['id']: entry for entry in spec['files']}
    spec_index = {entry['id']: index for index, entry in enumerate(spec['files'])}
    base_index = {entry['base']: entry['id'] for entry in spec['files']}
    out_dir = arguments.out
    files_dir = out_dir / 'files'
    files_dir.mkdir(parents=True, exist_ok=True)

    failures = []
    assertions = 0
    per_file = []
    missing = []
    skipped = []
    duplicates = []
    seen_hashes = {}
    harness_checks = int(meta.get('checks', '0'))

    for base, entry_id in base_index.items():
        if not (arguments.corpus / base).exists():
            missing.append(base)
    measured_bases = set()
    for index in order:
        item = measurements[index]
        if item.file is None:
            failures.append('index %d carries no file record' % index)
            continue
        base = item.file['base']
        measured_bases.add(base)
        if base not in base_index:
            failures.append('measured file %r is absent from the spec' % base)
        elif base_index[base] != item.file['id']:
            failures.append('file id mismatch for %r' % base)

    for entry in spec['files']:
        entry_id = entry['id']
        index = spec_index[entry_id]
        item = measurements.get(index)
        verdict = Verdict()
        record = {
            'id': entry_id, 'base': entry['base'], 'category': entry['category'],
            'expect': entry['expect'], 'op': entry['op'], 'notes': entry['notes'],
            'font_role': entry['font_role'],
            'spec_sha256': entry['sha256'], 'spec_size': entry['size'],
            'changes': entry['changes'],
        }
        if item is None or item.file is None:
            skipped.append(entry['base'])
            record['result'] = 'skipped'
            record['failures'] = ['no measurements recorded']
            per_file.append(record)
            continue
        path = arguments.corpus / entry['base']
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ''
        record['input'] = {'size': item.file['size'], 'fnv': item.file['fnv'],
                           'sha256': digest, 'measured_size': item.file['size']}
        verdict.check(digest == entry['sha256'],
                      'input sha256 %s != frozen %s' % (digest[:16], entry['sha256'][:16]))
        verdict.check(item.file['size'] == entry['size'],
                      'input size %d != frozen %d' % (item.file['size'], entry['size']))
        if digest in seen_hashes:
            duplicates.append({'base': entry['base'], 'same_as': seen_hashes[digest]})
        seen_hashes[digest] = entry['base']
        verdict.check(item.file['size'] == path.stat().st_size if path.exists() else False,
                      'reported size disagrees with the file on disk')
        read = item.reads.get('in')
        record['read'] = read
        if entry['expect'] == 'read-fail':
            verdict.check(read is not None and read['status'] == entry['status'],
                          'read status %r != %r' % (read['status'] if read else None, entry['status']))
            verdict.check(item.need.get('in', {'present': False})['present'] == entry['need_appearances']['present'],
                          'NeedAppearances presence %r != frozen %r' %
                          (item.need.get('in', {}).get('present'), entry['need_appearances']['present']))
        else:
            verdict.check(read is not None and read['status'] == 'EXR_OK',
                          'read status %r != EXR_OK' % (read['status'] if read else None))
            if entry['expect'] == 'empty':
                verdict.check(read is not None and read['fields'] == 0,
                              'expected an empty snapshot, saw %r' % (read['fields'] if read else None))
            else:
                compare_field_list(verdict, entry['fields'], item.fields['in'], 'read')
            need = item.need.get('in', {'present': False, 'value': False})
            verdict.check(need['present'] == entry['need_appearances']['present'],
                          'NeedAppearances presence %r != frozen %r' %
                          (need['present'], entry['need_appearances']['present']))
            if entry['need_appearances']['present']:
                verdict.check(need['value'] == entry['need_appearances']['value'],
                              'NeedAppearances value %r != frozen %r' %
                              (need['value'], entry['need_appearances']['value']))
        record['write'] = item.write
        if entry['expect'] in ('accept', 'empty'):
            if entry['op'] in ('write', 'write-empty'):
                verdict.check(item.write['status'] == 'EXR_OK',
                              'write status %r != EXR_OK (%s)' %
                              (item.write['status'], item.write.get('message')))
                verdict.check(item.write['prefix'], 'output does not preserve the input prefix')
                verdict.check(item.write['same'], 'the caller input bytes changed')
                verdict.check(item.write['size'] > entry['size'] if entry['op'] == 'write'
                              else item.write['size'] == entry['size'],
                              'output size %d unexpected' % item.write['size'])
                edited = arguments.edited / item.write['name']
                verdict.check(edited.exists(), 'edited output is missing: %s' % item.write['name'])
                if edited.exists():
                    record['edited'] = {'name': item.write['name'],
                                        'size': edited.stat().st_size,
                                        'sha256': hashlib.sha256(edited.read_bytes()).hexdigest()}
                    verdict.check(edited.stat().st_size == item.write['size'],
                                  'edited size %d != reported %d' %
                                  (edited.stat().st_size, item.write['size']))
                verdict.check(item.reopen is not None and item.reopen['status'] == 'EXR_OK',
                              'reopen status %r != EXR_OK' %
                              (item.reopen['status'] if item.reopen else None))
                expected_values, expected_indices = expected_after(entry)
                after = {field['name']: field for field in item.fields['out']}
                verdict.check(len(item.fields['out']) == len(entry['fields']),
                              'reopened field count %d != %d' %
                              (len(item.fields['out']), len(entry['fields'])))
                for name, values in expected_values.items():
                    verdict.check(name in after, 'reopened document lacks %r' % name)
                    if name in after:
                        verdict.check(after[name]['values'] == values,
                                      '%s: reopened values %r != expected %r' %
                                      (name, after[name]['values'], values))
                unchanged = [field['name'] for field in entry['fields']
                             if field['name'] not in expected_values]
                before = {field['name']: field for field in item.fields['in']}
                for name in unchanged:
                    if name in after and name in before:
                        verdict.check(after[name]['values'] == before[name]['values'],
                                      '%s: unedited values changed %r -> %r' %
                                      (name, before[name]['values'], after[name]['values']))
                states = {}
                for change in entry['changes']:
                    field = next((value for value in entry['fields']
                                  if value['name'] == change['field']), None)
                    if field is None:
                        continue
                    values = [value['hex'] if isinstance(value, dict) else value
                              for value in change['values']]
                    if field['kind'] in ('checkbox', 'radio'):
                        for widget_index, widget in enumerate(field['widgets']):
                            expected_state = values[0] if values and values[0] == widget['on_state'] else 'Off'
                            states[(change['field'], widget_index)] = expected_state
                verdict.check(len(item.annots['in']) == len(item.annots['out']),
                              'annotation count changed %d -> %d' %
                              (len(item.annots['in']), len(item.annots['out'])))
                edited_widgets = []
                for name in expected_values:
                    field = next((value for value in entry['fields'] if value['name'] == name), None)
                    if field is None:
                        continue
                    for widget in field['widgets']:
                        if widget['page'] is not None:
                            edited_widgets.append(widget)
                for before_annot, after_annot in zip(item.annots['in'], item.annots['out']):
                    if annot_match(edited_widgets, after_annot) is not None:
                        continue
                    verdict.check(before_annot['kind'] == after_annot['kind'] and
                                  before_annot['hash'] == after_annot['hash'],
                                  'unedited annotation at page %d changed its appearance' %
                                  after_annot['page'])
                for (name, widget_index), expected_state in states.items():
                    field = next((value for value in entry['fields'] if value['name'] == name), None)
                    widget = field['widgets'][widget_index]
                    if widget['page'] is None:
                        continue
                    match = annot_for_widget(item.annots['out'], widget)
                    verdict.check(match is not None,
                                  '%s widget %d: no annotation on page %d' %
                                  (name, widget_index, widget['page']))
                    if match is not None:
                        verdict.check(match['state'] == expected_state,
                                      '%s widget %d: AS %r != %r' %
                                      (name, widget_index, match['state'], expected_state))
                        verdict.check(match['kind'] == 'dict' or
                                      (match['kind'] == 'stream' and match['length'] > 0),
                                      '%s widget %d: appearance is empty' % (name, widget_index))
                ink_by_field = {}
                for ink in item.ink:
                    ink_by_field.setdefault(ink['field'], []).append(ink)
                for change in entry['changes']:
                    field = next((value for value in entry['fields']
                                  if value['name'] == change['field']), None)
                    if field is None:
                        continue
                    values = [value['hex'] if isinstance(value, dict) else value
                              for value in change['values']]
                    for widget_index, widget in enumerate(field['widgets']):
                        if widget['page'] is None:
                            continue
                        entries = [ink for ink in ink_by_field.get(change['field'], [])
                                   if ink['widget'] == widget_index]
                        verdict.check(len(entries) == 1,
                                      '%s widget %d: no ink measurement' % (change['field'], widget_index))
                        if not entries:
                            continue
                        if field['kind'] in ('checkbox', 'radio'):
                            expect_ink = bool(values) and values[0] == widget['on_state']
                        else:
                            expect_ink = bool(values and values[0].strip())
                        verdict.check((entries[0]['dark'] > 0) == expect_ink,
                                      '%s widget %d: ink %d does not match expected %s (%s)' %
                                      (change['field'], widget_index, entries[0]['dark'],
                                       'ink' if expect_ink else 'none',
                                       entries[0].get('message')))
                record['ink'] = item.ink
            else:
                verdict.check(read is not None and read['status'] == 'EXR_OK',
                              'read of a formless document was not successful')
        else:
            if item.write is not None:
                verdict.check(item.write['status'] == entry['status'],
                              'write status %r != %r (%s)' %
                              (item.write['status'], entry['status'], item.write.get('message')))
                verdict.check(item.write['size'] == 0 and
                              item.write['changes'] == len(entry['changes']),
                              'rejected write reported outputs or a wrong change count')
                verdict.check(item.write['same'], 'a rejected write modified the caller input')
            else:
                verdict.check(entry['expect'] == 'read-fail',
                              'no write was attempted for a writable document')
            if entry['expect'] in ('reject', 'cancel'):
                verdict.check(item.repeat is not None,
                              'missing repeat-call record')
                if item.repeat is not None:
                    verdict.check(item.repeat['first'] == item.repeat['second'] == entry['status'],
                                  'repeat call status %r/%r != %r' %
                                  (item.repeat['first'], item.repeat['second'], entry['status']))
                    verdict.check(item.repeat['noop'] == 'EXR_OK',
                                  'zero-change write after a refusal returned %r' % item.repeat['noop'])
                    verdict.check(item.repeat['noop_size'] == entry['size'],
                                  'zero-change copy size %d != %d' %
                                  (item.repeat['noop_size'], entry['size']))
                    verdict.check(item.repeat['noop_same'],
                                  'zero-change copy differs from the input')
        reference_record = reference_files.get(entry_id)
        if reference_record is not None:
            record['reference'] = {
                'checks': reference_record.get('checks', []),
                'problems': reference_record.get('problems', []),
                'qpdf': reference_record.get('qpdf'),
                'qpdf_output': reference_record.get('qpdf_output'),
                'render': reference_record.get('render'),
                'ink': reference_record.get('ink'),
            }
            for problem in reference_record.get('problems', []):
                verdict.check(False, 'reference: %s' % problem)
            if entry['expect'] in ('accept', 'empty') and entry['op'] == 'write':
                verdict.check('pypdf field tree' in reference_record.get('checks', []),
                              'reference did not cross-check the field tree')
                verdict.check('poppler raster ink' in reference_record.get('checks', []),
                              'reference did not rasterise the edited output')
        record['assertions'] = verdict.assertions
        record['result'] = 'pass' if not verdict.failures else 'fail'
        record['failures'] = verdict.failures
        assertions += verdict.assertions
        failures.extend('%s %s: %s' % (entry_id, entry['base'], message)
                        for message in verdict.failures)
        (files_dir / (entry_id + '.json')).write_text(
            json.dumps(record, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        per_file.append(record)

    extra = sorted(measured_bases - set(base_index))
    for base in extra:
        failures.append('measured file %r has no spec entry' % base)

    counts = {
        'files': len(spec['files']),
        'measured_files': len(measured_bases),
        'accept': sum(1 for record in per_file if record['expect'] in ('accept', 'empty')),
        'reject': sum(1 for record in per_file if record['expect'] == 'reject'),
        'cancel': sum(1 for record in per_file if record['expect'] == 'cancel'),
        'read_fail': sum(1 for record in per_file if record['expect'] == 'read-fail'),
        'passed': sum(1 for record in per_file if record['result'] == 'pass'),
        'failed': sum(1 for record in per_file if record['result'] == 'fail'),
        'skipped': len(skipped),
        'missing': len(missing),
        'duplicate_content': len(duplicates),
        'fields': sum(len(record['fields']) for record in spec['files'] if 'fields' in record),
        'widgets': sum(len(field['widgets']) for record in spec['files'] if 'fields' in record
                       for field in record['fields']),
        'assertions': assertions,
        'harness_checks': harness_checks,
    }
    if counts['files'] < 30:
        failures.append('corpus holds %d files below the 30 file gate' % counts['files'])
    if missing:
        failures.append('%d spec files are missing from the corpus directory' % len(missing))
    if skipped:
        failures.append('%d files produced no measurements' % len(skipped))
    if duplicates:
        failures.append('%d files share content with another file' % len(duplicates))
    if arguments.require_reference and reference is None:
        failures.append('the independent reference report is missing')
    if reference is not None:
        for problem in reference.get('failures', []):
            failures.append('reference: %s' % problem)

    manifest = {
        'schema': 'exreader-acroform-corpus-evidence/1',
        'platform': arguments.platform,
        'results_sha256': hashlib.sha256(arguments.results.read_bytes()).hexdigest(),
        'spec_plan_sha256': spec.get('plan_sha256'),
        'counts': counts,
        'files': [{'base': record['base'], 'id': record['id'],
                   'category': record['category'], 'expect': record['expect'],
                   'size': record.get('input', {}).get('size'),
                   'sha256': record.get('input', {}).get('sha256'),
                   'edited_sha256': record.get('edited', {}).get('sha256'),
                   'assertions': record.get('assertions', 0),
                   'result': record.get('result', 'skipped'),
                   'failures': record.get('failures', [])} for record in per_file],
        'missing': missing, 'skipped': skipped, 'duplicates': duplicates,
        'extra': extra,
        'failure_count': len(failures),
    }
    (out_dir / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    summary = ['# WP9 AcroForm independent corpus evidence', '',
               'Platform: %s' % arguments.platform,
               '',
               '| files | accept | reject | cancel | read-fail | passed | failed | skipped |',
               '| --- | --- | --- | --- | --- | --- | --- | --- |',
               '| %d | %d | %d | %d | %d | %d | %d | %d |' % (
                   counts['files'], counts['accept'], counts['reject'], counts['cancel'],
                   counts['read_fail'], counts['passed'], counts['failed'], counts['skipped']),
               '',
               'Assertions: %d. C harness CHECK executions: %d. Fields: %d. Widgets: %d.' % (
                   counts['assertions'], counts['harness_checks'], counts['fields'], counts['widgets']),
               '']
    if failures:
        summary.append('## Failures')
        summary.extend('- %s' % failure for failure in failures[:200])
    (out_dir / 'summary.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    print(json.dumps(counts, indent=1))
    for failure in failures[:40]:
        print('FAIL ' + failure, file=sys.stderr)
    return 0 if not failures else 1


if __name__ == '__main__':
    raise SystemExit(main())

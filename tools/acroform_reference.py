#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Independent reference checks for the WP9 AcroForm corpus.

This tool never imports the project.  It reads the frozen corpus with three
outside implementations and compares their answer with the frozen spec:

* qpdf        - structural validator for every input and edited output
* pypdf       - separate AcroForm reader: qualified names, values, flags,
                MaxLen, Opt pairs, widget counts and button states
* poppler     - separate rasteriser: pdftoppm ink inside each edited widget

Both the spec and the measurement are recorded so the summary can show which
tool, which version and which comparison produced a verdict.  The scripts run
only inside GitHub Actions; the local tree only carries the source.

Modes
  inputs   validate every corpus PDF before the implementation reads it
  outputs  validate the edited PDFs the implementation produced

Usage
  acroform_reference.py inputs  --corpus DIR --out FILE
  acroform_reference.py outputs --corpus DIR --edited DIR --results TSV --out FILE
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

RESOLUTION = 150
INK_LEVEL = 100
INSET = 3.0


def run(command, timeout=300):
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    return {
        'command': ' '.join(str(part) for part in command),
        'exit': result.returncode,
        'stdout': result.stdout.decode('utf-8', 'replace'),
        'stderr': result.stderr.decode('utf-8', 'replace'),
    }


def tool_versions():
    versions = {}
    for name, command in (('qpdf', ['qpdf', '--version']), ('poppler', ['pdftoppm', '-v'])):
        path = shutil.which(command[0])
        if not path:
            versions[name] = {'available': False}
            continue
        try:
            result = run(command)
            text = (result['stdout'] + result['stderr']).strip().splitlines()
        except OSError as error:
            versions[name] = {'available': False, 'error': str(error)}
            continue
        versions[name] = {'available': True, 'path': path,
                          'version': text[0] if text else 'unknown'}
    try:
        import pypdf
        versions['pypdf'] = {'available': True, 'version': getattr(pypdf, '__version__', 'unknown')}
    except ImportError as error:
        versions['pypdf'] = {'available': False, 'error': str(error)}
    return versions


def qpdf_check(path):
    executable = shutil.which('qpdf')
    if not executable:
        return {'available': False}
    result = run([executable, '--check', str(path)])
    return {
        'available': True,
        'exit': result['exit'],
        'errors': result['stdout'].count('ERROR'),
        'warnings': result['stdout'].count('WARNING'),
        'output': (result['stdout'] + result['stderr']).strip()[:4000],
        'passed': result['exit'] in (0, 3),
    }


def resolve(value):
    if value is not None and hasattr(value, 'get_object'):
        try:
            return value.get_object()
        except AttributeError:
            return value
    return value


def as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).lstrip('/') for item in value]
    return [str(value).lstrip('/')]


def pypdf_fields(path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    fields = reader.get_fields()
    if not fields:
        return {}
    out = {}
    for name, field in fields.items():
        raw = field.get('/V')
        kids = field.get('/Kids')
        options = []
        opt = field.get('/Opt')
        if opt:
            for item in opt:
                if isinstance(item, (list, tuple)):
                    pair = [str(part) for part in item]
                    options.append([pair[0], pair[1] if len(pair) > 1 else pair[0]])
                else:
                    options.append([str(item), str(item)])
        states = field.get('/_States_') or []
        out[str(name)] = {
            'values': as_list(raw),
            'flags': int(field.get('/Ff') or 0),
            'max_length': int(field.get('/MaxLen') or 0),
            'options': options,
            'widgets': len(kids) if kids else 1,
            'states': [str(state).lstrip('/') for state in states],
            'indices': as_list(field.get('/I')),
        }
    return out


def normalise_values(values):
    return [str(value) for value in values]


def option_values(field):
    return [option['value'] for option in field['options']]


def expected_after_values(entry):
    """Reopened values and option indexes the writer is required to produce."""
    values_out = {}
    indices_out = {}
    for change in entry['changes']:
        field = next((item for item in entry['fields'] if item['name'] == change['field']), None)
        values = [value['hex'] if isinstance(value, dict) else value for value in change['values']]
        if field is None:
            continue
        if field['kind'] in ('checkbox', 'radio'):
            values_out[change['field']] = values[:1]
        elif field['kind'] == 'choice':
            names = option_values(field)
            if field['flags'] & (1 << 21):
                ordered = [name for name in names if name in values]
                values_out[change['field']] = ordered
                indices_out[change['field']] = [names.index(name) for name in ordered]
            else:
                values_out[change['field']] = values[:1]
                indices_out[change['field']] = [names.index(values[0])] if values and values[0] in names else []
        else:
            values_out[change['field']] = values[:1] if values else ['']
    return values_out, indices_out


def compare_fields(expected, actual):
    problems = []
    expected_names = [field['name'] for field in expected]
    actual_names = list(actual.keys())
    for name in expected_names:
        if name not in actual:
            problems.append('pypdf missing field %r' % name)
    for name in actual_names:
        if name not in expected_names:
            problems.append('pypdf extra field %r' % name)
    for field in expected:
        name = field['name']
        if name not in actual:
            continue
        found = actual[name]
        if normalise_values(found['values']) != normalise_values(field['values']):
            problems.append('%s: pypdf values %r != spec %r' %
                            (name, found['values'], field['values']))
        if found['flags'] != field['flags']:
            problems.append('%s: pypdf flags %d != spec %d' % (name, found['flags'], field['flags']))
        if field['max_length'] and found['max_length'] != field['max_length']:
            problems.append('%s: pypdf MaxLen %d != spec %d' %
                            (name, found['max_length'], field['max_length']))
        if field['kind'] == 'choice':
            expected_options = [[option['value'], option['label']] for option in field['options']]
            if found['options'] != expected_options:
                problems.append('%s: pypdf Opt %r != spec %r' %
                                (name, found['options'], expected_options))
        separate = sum(1 for widget in field['widgets'] if not widget.get('merged'))
        expected_widgets = separate if separate else 1
        if found['widgets'] != expected_widgets:
            problems.append('%s: pypdf widgets %d != spec %d' %
                            (name, found['widgets'], expected_widgets))
        if field['kind'] in ('checkbox', 'radio'):
            expected_states = sorted(set(widget['on_state'] for widget in field['widgets']
                                         if widget['on_state']))
            if expected_states and found['states'] and sorted(found['states']) != expected_states:
                problems.append('%s: pypdf states %r != spec %r' %
                                (name, found['states'], expected_states))
    return problems


def parse_pgm(path):
    data = pathlib.Path(path).read_bytes()
    if not data.startswith(b'P5'):
        raise ValueError('not a binary PGM: %s' % path)
    index = 2
    tokens = []
    while len(tokens) < 3:
        while index < len(data) and data[index:index + 1].isspace():
            index += 1
        if data[index:index + 1] == b'#':
            while data[index:index + 1] not in (b'\n', b''):
                index += 1
            continue
        start = index
        while index < len(data) and not data[index:index + 1].isspace():
            index += 1
        tokens.append(int(data[start:index]))
    index += 1
    width, height, _maximum = tokens
    return width, height, data[index:]


def ink_in_rect(image, width, rect, page_height, inset=INSET):
    scale = RESOLUTION / 72.0
    x0 = int(round((rect[0] + inset) * scale))
    x1 = int(round((rect[2] - inset) * scale))
    y0 = int(round((page_height - rect[3] + inset) * scale))
    y1 = int(round((page_height - rect[1] - inset) * scale))
    x0 = max(0, min(width, x0))
    x1 = max(0, min(width, x1))
    dark = 0
    total = 0
    for y in range(max(0, y0), max(0, y1)):
        row = y * width
        for x in range(max(0, x0), max(0, x1)):
            total += 1
            if image[row + x] < INK_LEVEL:
                dark += 1
    return dark, total


def render_pages(pdf, workdir, tag):
    executable = shutil.which('pdftoppm')
    if not executable:
        return None, {'available': False}
    prefix = workdir / ('page-' + tag)
    for stale in workdir.glob(prefix.name + '-*.pgm'):
        stale.unlink()
    result = run([executable, '-gray', '-r', str(RESOLUTION), str(pdf), str(prefix)])
    pages = sorted(workdir.glob(prefix.name + '-*.pgm'))
    return pages, {'available': True, 'exit': result['exit'],
                   'pages': len(pages),
                   'stderr': result['stderr'].strip()[:2000]}


def hex_text_operands(data):
    found = []
    for match in re.finditer(rb'<([0-9A-Fa-f]+)>\s*Tj', data):
        try:
            found.append(bytes.fromhex(match.group(1).decode('ascii')))
        except ValueError:
            continue
    return found


def main():
    parser = argparse.ArgumentParser(description='Independent AcroForm corpus reference checks')
    parser.add_argument('mode', choices=['inputs', 'outputs'])
    parser.add_argument('--corpus', required=True, type=pathlib.Path)
    parser.add_argument('--edited', type=pathlib.Path)
    parser.add_argument('--results', type=pathlib.Path)
    parser.add_argument('--out', required=True, type=pathlib.Path)
    parser.add_argument('--workdir', type=pathlib.Path)
    arguments = parser.parse_args()
    spec = json.loads((arguments.corpus / 'corpus-spec.json').read_text(encoding='utf-8'))
    workdir = arguments.workdir or (arguments.out.parent / 'reference-pages')
    workdir.mkdir(parents=True, exist_ok=True)
    versions = tool_versions()
    report = {
        'schema': 'exreader-acroform-reference/1',
        'mode': arguments.mode,
        'tools': versions,
        'resolution_dpi': RESOLUTION,
        'ink_level': INK_LEVEL,
        'inset_points': INSET,
        'files': [],
        'failures': [],
    }
    if not versions['qpdf']['available']:
        report['failures'].append('qpdf is not installed')
    if not versions['pypdf']['available']:
        report['failures'].append('pypdf is not installed')

    if arguments.mode == 'outputs':
        from pypdf import PdfReader

    for entry in spec['files']:
        record = {'id': entry['id'], 'base': entry['base'], 'category': entry['category'],
                  'expect': entry['expect'], 'checks': [], 'problems': []}
        source = arguments.corpus / entry['base']
        record['input_bytes'] = source.stat().st_size if source.exists() else 0
        record['qpdf'] = qpdf_check(source)
        if record['qpdf'].get('available') and not record['qpdf']['passed']:
            record['problems'].append('qpdf --check rejected the input: exit %d' % record['qpdf']['exit'])
        if entry['expect'] in ('reject', 'cancel', 'read-fail'):
            record['pypdf'] = {'skipped': 'negative case; readers must agree on the refusal'}
            report['files'].append(record)
            report['failures'].extend('%s: %s' % (entry['id'], problem)
                                      for problem in record['problems'])
            continue
        try:
            actual = pypdf_fields(source)
        except Exception as error:  # noqa: BLE001 - the reference tool is under test too
            record['pypdf'] = {'error': repr(error)}
            record['problems'].append('pypdf could not read the field tree: %r' % (error,))
            actual = None
        if actual is not None:
            problems = compare_fields(entry['fields'], actual)
            record['pypdf'] = {'field_count': len(actual),
                               'names': sorted(actual.keys()),
                               'problems': problems}
            record['problems'].extend(problems)
            record['checks'].append('pypdf field tree')
        if arguments.mode == 'inputs':
            report['files'].append(record)
            report['failures'].extend('%s: %s' % (entry['id'], problem)
                                      for problem in record['problems'])
            continue

        output = None
        if arguments.edited:
            output = arguments.edited / (source.stem + '.edited.pdf')
        if output is None or not output.exists():
            record['problems'].append('edited output is missing')
            report['files'].append(record)
            report['failures'].extend('%s: %s' % (entry['id'], problem)
                                      for problem in record['problems'])
            continue
        try:
            reader = PdfReader(str(output))
        except Exception as error:  # noqa: BLE001
            record['problems'].append('pypdf could not open the edited output: %r' % (error,))
            report['files'].append(record)
            report['failures'].extend('%s: %s' % (entry['id'], problem)
                                      for problem in record['problems'])
            continue
        record['output_bytes'] = output.stat().st_size
        record['qpdf_output'] = qpdf_check(output)
        if record['qpdf_output'].get('available') and not record['qpdf_output']['passed']:
            record['problems'].append('qpdf --check rejected the edited output: exit %d' %
                                      record['qpdf_output']['exit'])
        try:
            after = pypdf_fields(output)
        except Exception as error:  # noqa: BLE001
            after = None
            record['problems'].append('pypdf could not read the edited output: %r' % (error,))
        if after is not None:
            expected_after, expected_indices = expected_after_values(entry)
            record['pypdf_output'] = {'field_count': len(after)}
            for name, values in expected_after.items():
                if name not in after:
                    record['problems'].append('pypdf output missing field %r' % name)
                    continue
                if normalise_values(after[name]['values']) != normalise_values(values):
                    record['problems'].append('%s: pypdf output values %r != expected %r' %
                                              (name, after[name]['values'], values))
            record['checks'].append('pypdf edited values')
            for name, indices in expected_indices.items():
                if name not in after:
                    continue
                if after[name]['indices'] != [str(value) for value in indices]:
                    record['problems'].append('%s: pypdf /I %r != expected %r' %
                                              (name, after[name]['indices'], indices))
                record['checks'].append('pypdf option index')
        # Appearance text inside the written normal appearance stream.
        for change in entry['changes']:
            field = next((item for item in entry['fields'] if item['name'] == change['field']), None)
            if field is None or field['kind'] not in ('text', 'choice'):
                continue
            if field['kind'] == 'choice':
                labels = []
                for value in change['values']:
                    match = next((option['label'] for option in field['options']
                                  if option['value'] == value), None)
                    if match is None:
                        labels = None
                        break
                    labels.append(match)
                expected_texts = labels or []
            else:
                expected_texts = [str(value) for value in change['values']]
            if not all(text.isascii() for text in expected_texts):
                continue
            try:
                blobs = []
                rects = [widget['rect'] for widget in field['widgets']]
                for page in reader.pages:
                    annotations = page.get('/Annots') or []
                    for annotation in annotations:
                        widget = resolve(annotation)
                        rect = widget.get('/Rect')
                        if not rect:
                            continue
                        corners = [float(value) for value in rect]
                        if not any(all(abs(corners[index] - target[index]) < 0.5 for index in range(4))
                                   for target in rects):
                            continue
                        ap = resolve(widget.get('/AP'))
                        if not ap:
                            continue
                        normal = resolve(ap.get('/N'))
                        if normal is None or not hasattr(normal, 'get_data'):
                            continue
                        blobs.append(normal.get_data())
                texts = []
                for blob in blobs:
                    texts.extend(hex_text_operands(blob))
                joined = b' '.join(texts)
                record['appearance_text'] = {'expected': expected_texts,
                                             'streams': len(blobs), 'found': len(texts)}
                for text in expected_texts:
                    if text and text.encode('utf-8') not in joined:
                        record['problems'].append('%s: appearance stream lacks text %r' %
                                                  (change['field'], text))
                record['checks'].append('appearance stream text')
            except Exception as error:  # noqa: BLE001
                record['problems'].append('appearance stream inspection failed: %r' % (error,))
        # Independent raster ink inside every edited widget.
        pages, render = render_pages(output, workdir, entry['id'])
        record['render'] = render
        if pages:
            page_sizes = {}
            for page in pages:
                width, height, image = parse_pgm(page)
                number = int(page.stem.rsplit('-', 1)[1]) - 1
                page_sizes[number] = (width, height, image)
            record['ink'] = []
            for change in entry['changes']:
                field = next((item for item in entry['fields'] if item['name'] == change['field']), None)
                if field is None:
                    continue
                for index, widget in enumerate(field['widgets']):
                    if widget['page'] is None:
                        continue
                    page = page_sizes.get(widget['page'])
                    if page is None:
                        record['problems'].append('%s: renderer produced no page %d' %
                                                  (change['field'], widget['page']))
                        continue
                    width, height, image = page
                    dark, total = ink_in_rect(image, width, widget['rect'], spec['page_size'][1])
                    if field['kind'] in ('checkbox', 'radio'):
                        on_state = widget['on_state']
                        selected = bool(change['values']) and change['values'][0] == on_state
                        expect_ink = selected
                    else:
                        text = change['values'][0] if change['values'] else ''
                        expect_ink = bool(text.strip())
                    record['ink'].append({'field': change['field'], 'widget': index,
                                          'page': widget['page'], 'dark': dark, 'pixels': total,
                                          'expect': 'ink' if expect_ink else 'none'})
                    if expect_ink and dark == 0:
                        record['problems'].append('%s widget %d: renderer shows no ink' %
                                                  (change['field'], index))
                    if not expect_ink and dark != 0:
                        record['problems'].append('%s widget %d: renderer shows unexpected ink (%d)' %
                                                  (change['field'], index, dark))
            record['checks'].append('poppler raster ink')
        else:
            record['problems'].append('pdftoppm produced no page images')
        report['files'].append(record)
        report['failures'].extend('%s: %s' % (entry['id'], problem)
                                  for problem in record['problems'])

    report['summary'] = {
        'files': len(report['files']),
        'checks': sum(len(record['checks']) for record in report['files']),
        'problems': len(report['failures']),
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n',
                             encoding='utf-8', newline='\n')
    print(json.dumps(report['summary'], indent=1))
    for failure in report['failures'][:40]:
        print('FAIL ' + failure, file=sys.stderr)
    return 0 if not report['failures'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

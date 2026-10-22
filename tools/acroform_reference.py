#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Independent reference checks for the WP9 AcroForm corpus.

This tool never imports the project.  Three outside implementations read the
same bytes and their answers are compared with the frozen spec:

* qpdf    - structural validation of every input and every edited output
* pypdf   - a separate AcroForm walker written against pypdf's parser.  It
            resolves the field tree itself, applies the inherited FT/Ff/V/DV/
            MaxLen/Opt entries, reports terminal fields only, and returns the
            widget set, the button on states, the option index and the written
            appearance stream of every widget.
* poppler - an independent rasteriser.  pdftoppm paints the edited output and
            the ink inside each edited widget is counted from the PGM.

Modes
  inputs   validate every corpus PDF before the implementation reads it
  outputs  validate the edited PDFs the implementation produced

Usage
  acroform_reference.py inputs  --corpus DIR --out FILE
  acroform_reference.py outputs --corpus DIR --edited DIR --out FILE
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
INHERITED = ('/FT', '/Ff', '/V', '/DV', '/DA', '/Q', '/MaxLen', '/Opt')


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


def is_dictionary(value):
    return value is not None and hasattr(value, 'keys') and hasattr(value, 'get')


def read_fields(path):
    """Walk the AcroForm tree through pypdf, applying field inheritance."""
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    root = resolve(reader.trailer['/Root'])
    acroform = resolve(root.get('/AcroForm')) if root.get('/AcroForm') is not None else None
    fields = {}
    streams = {}
    if not is_dictionary(acroform):
        return fields, streams
    base = {key: acroform.get(key) for key in INHERITED}

    def record_widget(widget):
        info = {'states': [], 'ap': None, 'rect': None}
        rect = widget.get('/Rect')
        if rect is not None:
            info['rect'] = [float(value) for value in rect]
        appearance = resolve(widget.get('/AP'))
        if is_dictionary(appearance):
            normal = resolve(appearance.get('/N'))
            if is_dictionary(normal):
                for key in normal.keys():
                    text = str(key).lstrip('/')
                    if text != 'Off' and text not in info['states']:
                        info['states'].append(text)
            elif normal is not None and hasattr(normal, 'get_data'):
                info['ap'] = normal.get_data()
        return info

    def walk(node, prefix, inherited):
        local = dict(inherited)
        for key in INHERITED:
            if node.get(key) is not None:
                local[key] = node.get(key)
        raw_name = node.get('/T')
        name = prefix
        if raw_name is not None and str(raw_name):
            name = (prefix + '.' + str(raw_name)) if prefix else str(raw_name)
        kids = [resolve(kid) for kid in (node.get('/Kids') or [])]
        widget_kids, field_kids = [], []
        for kid in kids:
            subtype = str(kid.get('/Subtype') or '')
            if (subtype == '/Widget' and kid.get('/T') is None and kid.get('/FT') is None
                    and kid.get('/Kids') is None):
                widget_kids.append(kid)
            else:
                field_kids.append(kid)
        if field_kids:
            for kid in field_kids:
                walk(kid, name, local)
            return
        if not name:
            return
        widgets = []
        if str(node.get('/Subtype') or '') == '/Widget':
            widgets.append(record_widget(node))
        widgets.extend(record_widget(kid) for kid in widget_kids)
        options = []
        raw_options = local.get('/Opt')
        if raw_options is not None:
            for item in raw_options:
                if isinstance(item, (list, tuple)):
                    pair = [str(part) for part in item]
                    options.append([pair[0], pair[1] if len(pair) > 1 else pair[0]])
                else:
                    options.append([str(item), str(item)])
        fields[name] = {
            'values': as_list(local.get('/V')),
            'flags': int(local.get('/Ff') or 0),
            'max_length': int(local.get('/MaxLen') or 0),
            'options': options,
            'indices': as_list(node.get('/I')) if node.get('/I') is not None else [],
            'states': sorted(set(state for widget in widgets for state in widget['states'])),
            'widgets': len(widgets),
        }
        blobs = [widget['ap'] for widget in widgets if widget['ap']]
        if blobs:
            streams[name] = blobs

    for node in (acroform.get('/Fields') or []):
        walk(resolve(node), '', base)
    return fields, streams


def compare_fields(expected, actual):
    problems = []
    names = [field['name'] for field in expected]
    for name in names:
        if name not in actual:
            problems.append('pypdf missing field %r' % name)
    for name in actual:
        if name not in names:
            problems.append('pypdf extra field %r' % name)
    for field in expected:
        name = field['name']
        if name not in actual:
            continue
        found = actual[name]
        if [str(value) for value in found['values']] != [str(value) for value in field['values']]:
            problems.append('%s: pypdf values %r != spec %r' %
                            (name, found['values'], field['values']))
        if found['flags'] != field['flags']:
            problems.append('%s: pypdf flags %d != spec %d' % (name, found['flags'], field['flags']))
        if found['max_length'] != field['max_length']:
            problems.append('%s: pypdf MaxLen %d != spec %d' %
                            (name, found['max_length'], field['max_length']))
        if field['kind'] == 'choice':
            wanted = [[option['value'], option['label']] for option in field['options']]
            if found['options'] != wanted:
                problems.append('%s: pypdf Opt %r != spec %r' % (name, found['options'], wanted))
        if found['widgets'] != len(field['widgets']):
            problems.append('%s: pypdf widgets %d != spec %d' %
                            (name, found['widgets'], len(field['widgets'])))
        wanted_states = sorted(set(widget['on_state'] for widget in field['widgets']
                                   if widget['on_state']))
        if wanted_states != found['states']:
            problems.append('%s: pypdf states %r != spec %r' %
                            (name, found['states'], wanted_states))
    return problems


def option_values(field):
    return [option['value'] for option in field['options']]


def expected_after_values(entry):
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
            while index < len(data) and data[index:index + 1] not in (b'\n', b''):
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
    dark = 0
    total = 0
    for y in range(max(0, y0), max(0, y1)):
        row = y * width
        for x in range(max(0, x0), max(0, x1)):
            total += 1
            if image[row + x] < INK_LEVEL:
                dark += 1
    return dark, total


def page_dark(image):
    return sum(1 for value in image if value < INK_LEVEL)


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

    for entry in spec['files']:
        record = {'id': entry['id'], 'base': entry['base'], 'category': entry['category'],
                  'expect': entry['expect'], 'checks': [], 'problems': []}
        source = arguments.corpus / entry['base']
        record['qpdf'] = qpdf_check(source)
        if record['qpdf'].get('available') and not record['qpdf']['passed']:
            record['problems'].append('qpdf --check rejected the input: exit %d' % record['qpdf']['exit'])
        if entry['expect'] in ('reject', 'cancel', 'read-fail'):
            record['pypdf'] = {'skipped': 'negative case; the reference only checks structure'}
            report['files'].append(record)
            report['failures'].extend('%s: %s' % (entry['id'], problem)
                                      for problem in record['problems'])
            continue
        try:
            actual, _streams = read_fields(source)
        except Exception as error:  # noqa: BLE001 - the reference tool is under test too
            record['pypdf'] = {'error': repr(error)}
            record['problems'].append('pypdf could not read the field tree: %r' % (error,))
            actual = None
        if actual is not None:
            problems = compare_fields(entry['fields'], actual)
            record['pypdf'] = {'field_count': len(actual), 'names': sorted(actual.keys()),
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
            record['problems'].append('edited output is missing: %s' %
                                      (source.stem + '.edited.pdf'))
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
            after, streams = read_fields(output)
        except Exception as error:  # noqa: BLE001
            after, streams = None, {}
            record['problems'].append('pypdf could not read the edited output: %r' % (error,))
        if after is not None:
            expected_after, expected_indices = expected_after_values(entry)
            record['pypdf_output'] = {'field_count': len(after)}
            for name, values in expected_after.items():
                if name not in after:
                    record['problems'].append('pypdf output missing field %r' % name)
                    continue
                if [str(value) for value in after[name]['values']] != [str(value) for value in values]:
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
            for name, values in expected_after.items():
                field = next((item for item in entry['fields'] if item['name'] == name), None)
                if field is None:
                    continue
                if field['kind'] in ('checkbox', 'radio'):
                    wanted = sorted(set(widget['on_state'] for widget in field['widgets']
                                        if widget['on_state']))
                    if after.get(name, {}).get('states') != wanted:
                        record['problems'].append('%s: pypdf edited states %r != %r' %
                                                  (name, after.get(name, {}).get('states'), wanted))
                    record['checks'].append('pypdf button states')
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
                    wanted_text = labels or []
                else:
                    wanted_text = [str(value) for value in change['values']]
                if not all(text.isascii() for text in wanted_text):
                    continue
                blobs = streams.get(change['field'], [])
                texts = []
                for blob in blobs:
                    texts.extend(hex_text_operands(blob))
                joined = b' '.join(texts)
                record['appearance_text'] = {'expected': wanted_text,
                                             'streams': len(blobs), 'found': len(texts)}
                for text in wanted_text:
                    if text and text.encode('utf-8') not in joined:
                        record['problems'].append('%s: appearance stream lacks text %r' %
                                                  (change['field'], text))
                record['checks'].append('appearance stream text')

        pages, render = render_pages(output, workdir, entry['id'])
        record['render'] = render
        if not pages:
            record['problems'].append('pdftoppm produced no page images')
            report['files'].append(record)
            report['failures'].extend('%s: %s' % (entry['id'], problem)
                                      for problem in record['problems'])
            continue
        page_images = {}
        for page in pages:
            width, height, image = parse_pgm(page)
            page_images[int(page.stem.rsplit('-', 1)[1]) - 1] = (width, height, image)
        record['ink'] = []
        need = entry['need_appearances']
        if need['present'] and need['value']:
            record['ink_note'] = ('poppler regenerates widget appearances when '
                                  'NeedAppearances is true, so raster ink is not asserted')
        for change in entry['changes']:
            field = next((item for item in entry['fields'] if item['name'] == change['field']), None)
            if field is None:
                continue
            for index, widget in enumerate(field['widgets']):
                if widget['page'] is None:
                    continue
                page = page_images.get(widget['page'])
                if page is None:
                    record['problems'].append('%s: renderer produced no page %d' %
                                              (change['field'], widget['page']))
                    continue
                width, height, image = page
                dark, total = ink_in_rect(image, width, widget['rect'], spec['page_size'][1])
                if field['kind'] in ('checkbox', 'radio'):
                    selected = bool(change['values']) and change['values'][0] == widget['on_state']
                    expect_ink = selected
                else:
                    text = change['values'][0] if change['values'] else ''
                    expect_ink = bool(str(text).strip())
                entry_ink = {'field': change['field'], 'widget': index,
                             'page': widget['page'], 'dark': dark, 'pixels': total,
                             'expect': 'ink' if expect_ink else 'none'}
                if record.get('ink_note'):
                    entry_ink['asserted'] = False
                record['ink'].append(entry_ink)
                if record.get('ink_note'):
                    continue
                if (dark > 0) != expect_ink:
                    inside, _unused = ink_in_rect(image, width, widget['rect'],
                                                  spec['page_size'][1], 0.0)
                    entry_ink['full_rect_dark'] = inside
                    entry_ink['page_dark'] = page_dark(image)
                    record['problems'].append(
                        '%s widget %d: renderer shows %d dark pixels in the inset region, '
                        '%d in the full rect and %d on the page (expected %s)' %
                        (change['field'], index, dark, inside, entry_ink['page_dark'],
                         'ink' if expect_ink else 'none'))
        record['checks'].append('poppler raster ink')
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
    for failure in report['failures'][:60]:
        print('FAIL ' + failure, file=sys.stderr)
    return 0 if not report['failures'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

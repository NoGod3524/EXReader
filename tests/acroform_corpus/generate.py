#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the frozen WP9 AcroForm acceptance corpus and its expectation spec.

Every document here is original: the module writes the PDF object graph itself,
so the corpus is reproducible in CI and carries no third-party publication.
The same table that emits the bytes declares the frozen expectations the C
implementation must match.  The generator writes corpus-spec.json before any
implementation reads a document, and the checker compares recorded measurements
against that file, so a run cannot report its own conclusions.

Generation is deterministic: no timestamps, no locale-dependent numbers, no
platform newlines and a /ID derived from the corpus id.  The workflow runs the
generator twice and compares both trees byte for byte.

Usage: generate.py --out DIR
"""

import argparse
import hashlib
import json
import pathlib

PAGE_W = 200
PAGE_H = 120

KEYS = ('ft', 'flags', 'v', 'dv', 'da', 'q', 'maxlen', 'opt')
TEXT_FLAGS = {
    'readonly': 1,
    'required': 2,
    'multiline': 1 << 12,
    'password': 1 << 13,
    'fileselect': 1 << 20,
    'comb': 1 << 24,
    'richtext': 1 << 25,
}
BUTTON_FLAGS = {
    'notoggle': 1 << 14,
    'radio': 1 << 15,
    'push': 1 << 16,
    'unison': 1 << 25,
}
CHOICE_FLAGS = {
    'combo': 1 << 17,
    'edit': 1 << 18,
    'multiselect': 1 << 21,
}


def pdf_text(value):
    """PDF text string: literal for printable ASCII, else UTF-16BE with BOM."""
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    try:
        raw = value.encode('ascii')
    except UnicodeEncodeError:
        raw = None
    if raw is not None and all(0x20 <= b < 0x7f for b in raw) \
            and not any(b in raw for b in b'()\\'):
        return b'(' + raw + b')'
    return b'<' + b'FEFF' + value.encode('utf-16-be').hex().upper().encode('ascii') + b'>'


def pdf_name(value):
    out = bytearray(b'/')
    for b in value.encode('ascii'):
        if b <= 32 or b >= 127 or b in b'()<>[]{}/%#':
            out += b'#%02X' % b
        else:
            out.append(b)
    return bytes(out)


def value_bytes(value):
    kind, payload = value
    if kind == 'text':
        return pdf_text(payload)
    if kind == 'name':
        return pdf_name(payload)
    if kind == 'list':
        return b'[' + b' '.join(pdf_text(x) for x in payload) + b']'
    if kind == 'ints':
        return b'[' + b' '.join(b'%d' % x for x in payload) + b']'
    if kind == 'raw':
        return payload
    raise ValueError('unknown value kind %r' % (kind,))


def option_pair(item):
    if isinstance(item, str):
        return item, item
    return item[0], item[1]


def option_bytes(options):
    parts = []
    for item in options:
        export, label = option_pair(item)
        if export == label:
            parts.append(pdf_text(export))
        else:
            parts.append(b'[' + pdf_text(export) + b' ' + pdf_text(label) + b']')
    return b'[' + b' '.join(parts) + b']'


def stream_body(extra, data):
    return b'<< ' + extra + b' /Length ' + b'%d' % len(data) + b' >>\nstream\n' + data + b'\nendstream'


def app_xobject(width, height, gray):
    paint = b'q %.3f g 0 0 %.3f %.3f re f Q\n' % (gray, width, height)
    return stream_body(b'/Type /XObject /Subtype /Form /FormType 1 '
                       b'/BBox [0 0 %.3f %.3f]' % (width, height), paint)


class Doc:
    """Deterministic PDF with an explicit object table."""

    def __init__(self, doc_id):
        self.objects = {}
        self.next = 1
        self.doc_id = doc_id
        self.page_annots = {}
        self.page_count = 1
        self.widgets = []

    def alloc(self):
        index = self.next
        self.next += 1
        return index

    def put(self, index, body):
        if not isinstance(body, bytes):
            body = body.encode('latin-1')
        self.objects[index] = body

    def finish(self, root=1):
        out = bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n')
        offsets = {}
        for oid in sorted(self.objects):
            offsets[oid] = len(out)
            out += b'%d 0 obj\n' % oid
            out += self.objects[oid]
            out += b'\nendobj\n'
        size = max(offsets) + 1
        xref = len(out)
        out += b'xref\n0 %d\n' % size
        out += b'0000000000 65535 f \n'
        for oid in range(1, size):
            if oid in offsets:
                out += b'%010d 00000 n \n' % offsets[oid]
            else:
                out += b'0000000000 00000 f \n'
        out += b'trailer\n<< /Size %d /Root %d 0 R /ID [<%s> <%s>] >>\n' % (
            size, root, self.doc_id,
            hashlib.sha256(self.doc_id + b'/id').hexdigest()[:16].encode('ascii'))
        out += b'startxref\n%d\n%%%%EOF\n' % xref
        return bytes(out)


def ref(index):
    return b'%d 0 R' % index


def alloc_node(doc, spec, parent_id, prefix, inherited, issues, xfa):
    node = {
        'spec': spec,
        'id': doc.alloc(),
        'parent': parent_id,
        'widgets': [],
        'children': [],
    }
    eff = dict(inherited)
    for key in KEYS:
        if key in spec:
            eff[key] = spec[key]
    node_issues = issues
    if spec.get('a') or spec.get('aa'):
        node_issues |= 1
    part = spec.get('t')
    name = part
    if prefix and part:
        name = prefix + '.' + part
    node['name'] = name
    node['effective'] = eff
    node['issues'] = node_issues
    widget = spec.get('widget')
    if widget is not None:
        entry = dict(widget)
        entry['id'] = node['id']
        entry['parent'] = node['id']
        entry['merged'] = True
        allocate_widget(doc, entry)
        node['widgets'].append(entry)
    for widget in spec.get('widgets') or ():
        entry = dict(widget)
        entry['id'] = doc.alloc()
        entry['parent'] = node['id']
        allocate_widget(doc, entry)
        node['widgets'].append(entry)
    for child in spec.get('kids') or ():
        node['children'].append(alloc_node(doc, child, node['id'], name, eff, node_issues, xfa))
    return node


def allocate_widget(doc, widget):
    ap = widget.get('ap')
    widget['ap_stream'] = None
    widget['ap_states'] = None
    if ap == 'stream':
        widget['ap_stream'] = doc.alloc()
    elif isinstance(ap, tuple) and ap[0] == 'dict':
        widget['ap_states'] = {state: doc.alloc() for state in ['Off'] + list(ap[1])}
    doc.widgets.append(widget)
    page = widget.get('page')
    if page is not None:
        doc.page_annots.setdefault(page, []).append(widget['id'])


def widget_body(widget):
    rect = widget['rect']
    body = [b'<< /Type /Annot /Subtype /Widget']
    if not widget.get('merged'):
        body.append(b' /Parent ' + ref(widget['parent']))
    body.append(b' /Rect [' + b' '.join(b'%g' % v for v in rect) + b']')
    if widget.get('ap_stream'):
        body.append(b' /AP << /N ' + ref(widget['ap_stream']) + b' >>')
    elif widget.get('ap_states'):
        inner = b' '.join(pdf_name(state) + b' ' + ref(widget['ap_states'][state])
                          for state in widget['ap_states'])
        body.append(b' /AP << /N << ' + inner + b' >> >>')
    if widget.get('as'):
        body.append(b' /AS ' + pdf_name(widget['as']))
    if widget.get('extra'):
        body.append(b' ' + widget['extra'])
    body.append(b' >>')
    return b''.join(body)


def on_state(widget):
    if widget.get('ap_states'):
        for state in widget['ap_states']:
            if state != 'Off':
                return state
    return None


def write_node(doc, node, output):
    spec = node['spec']
    body = [b'<<']
    if spec.get('t') is not None:
        body.append(b' /T ' + pdf_text(spec['t']))
    ft = spec.get('ft')
    if ft is not None:
        body.append(b' /FT /' + ft.encode('ascii'))
    for key, token in (('flags', 'Ff'), ('q', 'Q'), ('maxlen', 'MaxLen')):
        if key in spec:
            body.append(b' /' + token.encode('ascii') + b' %d' % spec[key])
    if 'v' in spec:
        body.append(b' /V ' + value_bytes(spec['v']))
    if 'dv' in spec:
        body.append(b' /DV ' + value_bytes(spec['dv']))
    if 'da' in spec:
        body.append(b' /DA ' + pdf_text(spec['da']))
    if 'opt' in spec:
        body.append(b' /Opt ' + option_bytes(spec['opt']))
    if node['parent'] is not None:
        body.append(b' /Parent ' + ref(node['parent']))
    kids = [child['id'] for child in node['children']] + \
           [w['id'] for w in node['widgets'] if not w.get('merged')]
    if kids:
        body.append(b' /Kids [' + b' '.join(ref(k) for k in kids) + b']')
    if spec.get('a'):
        body.append(b' /A << /S /JavaScript /JS (never executed) >>')
    if spec.get('aa'):
        body.append(b' /AA << /K << /S /JavaScript /JS (never executed) >> >>')
    if spec.get('extra'):
        body.append(b' ' + spec['extra'])
    body.append(b' >>')
    field_body = b''.join(body)
    for widget in node['widgets']:
        if widget.get('merged'):
            merged = widget_body(widget)
            field_body = field_body[:-3] + b' ' + merged[2:]
    doc.put(node['id'], field_body)
    for widget in node['widgets']:
        if not widget.get('merged'):
            doc.put(widget['id'], widget_body(widget))
    for child in node['children']:
        write_node(doc, child, output)


def kind_of(ft, flags):
    if ft == 'Tx':
        return 'text'
    if ft == 'Ch':
        return 'choice'
    if ft == 'Sig':
        return 'signature'
    if ft == 'Btn':
        if flags & BUTTON_FLAGS['push']:
            return 'pushbutton'
        if flags & BUTTON_FLAGS['radio']:
            return 'radio'
        return 'checkbox'
    return 'unknown'


def value_list(value):
    kind, payload = value
    if kind == 'text':
        return [payload]
    if kind == 'name':
        return [payload]
    if kind == 'list':
        return list(payload)
    if kind == 'ints':
        return [str(v) for v in payload]
    raise ValueError('unknown value kind %r' % (kind,))


def expect_node(node, xfa, output):
    if node['children']:
        for child in node['children']:
            expect_node(child, xfa, output)
        return
    eff = node['effective']
    ft = eff.get('ft')
    flags = eff.get('flags') or 0
    kind = kind_of(ft, flags)
    issues = node['issues']
    if xfa:
        issues |= 2
    if kind in ('signature', 'pushbutton', 'unknown'):
        issues |= 4
    readable = kind in ('text', 'checkbox', 'radio', 'choice')
    values = value_list(eff['v']) if readable and 'v' in eff else []
    defaults = value_list(eff['dv']) if readable and 'dv' in eff else []
    options = []
    if kind == 'choice':
        for item in eff.get('opt') or ():
            export, label = option_pair(item)
            options.append({'value': export, 'label': label})
    widgets = []
    for widget in node['widgets']:
        widgets.append({
            'page': widget.get('page'),
            'rect': [float(v) for v in widget['rect']],
            'on_state': on_state(widget),
            'merged': bool(widget.get('merged')),
        })
    output.append({
        'name': node['name'],
        'kind': kind,
        'flags': flags,
        'issues': issues,
        'max_length': eff.get('maxlen') or 0,
        'values': values,
        'defaults': defaults,
        'options': options,
        'widgets': widgets,
    })


def build_form(pages=1, fields=(), need='absent', page_size=(PAGE_W, PAGE_H),
               acro_extra=b'', catalog_extra=b'', acroform_direct=False,
               extra_annots=(), extra_objects=(), extra_field_arrays=b'',
               doc_id=b'0001', root_extra=b'', with_form=True):
    doc = Doc(doc_id)
    doc.page_count = pages
    catalog = doc.alloc()
    pages_id = doc.alloc()
    page_ids = [doc.alloc() for _ in range(pages)]
    acro_id = None if acroform_direct else doc.alloc()
    xfa = b'/XFA' in acro_extra
    roots = [alloc_node(doc, spec, None, '', {}, 0, xfa) for spec in fields]
    extra_annots_ids = {}
    for page, body in extra_annots:
        index = doc.alloc()
        doc.put(index, body)
        extra_annots_ids.setdefault(page, []).append(index)
    for body in extra_objects:
        doc.put(doc.alloc(), body)
    for root in roots:
        write_node(doc, root, [])
    for widget in doc.widgets:
        width = widget['rect'][2] - widget['rect'][0]
        height = widget['rect'][3] - widget['rect'][1]
        if widget.get('ap_stream'):
            doc.put(widget['ap_stream'], app_xobject(width, height, 0.75))
        if widget.get('ap_states'):
            for state, index in widget['ap_states'].items():
                doc.put(index, app_xobject(width, height, 0.9 if state == 'Off' else 0.2))
    for page in range(pages):
        body = b'<< /Type /Page /Parent ' + ref(pages_id) + \
               b' /MediaBox [0 0 %g %g]' % (page_size[0], page_size[1])
        annots = list(doc.page_annots.get(page, [])) + list(extra_annots_ids.get(page, []))
        if annots:
            body += b' /Annots [' + b' '.join(ref(a) for a in annots) + b']'
        body += b' >>'
        doc.put(page_ids[page], body)
    doc.put(pages_id, b'<< /Type /Pages /Kids [' + b' '.join(ref(p) for p in page_ids) +
            b'] /Count %d >>' % pages)
    need_text = b''
    if need is True:
        need_text = b' /NeedAppearances true'
    elif need is False:
        need_text = b' /NeedAppearances false'
    fields_array = b' /Fields [' + b' '.join(ref(root['id']) for root in roots) + b']'
    if extra_field_arrays:
        fields_array += b' ' + extra_field_arrays
    acro_body = b'<<' + fields_array + need_text + b' ' + acro_extra + b' >>'
    if not with_form:
        catalog_body = b'<< /Type /Catalog /Pages ' + ref(pages_id) + b' ' + catalog_extra + b' >>'
    elif acroform_direct:
        catalog_body = b'<< /Type /Catalog /Pages ' + ref(pages_id) + b' /AcroForm ' + \
                       acro_body + b' ' + catalog_extra + b' >>'
    else:
        doc.put(acro_id, acro_body)
        catalog_body = b'<< /Type /Catalog /Pages ' + ref(pages_id) + b' /AcroForm ' + \
                       ref(acro_id) + b' ' + catalog_extra + b' >>'
    doc.put(catalog, catalog_body + root_extra)
    expectations = []
    for root in roots:
        expect_node(root, xfa, expectations)
    return {
        'data': doc.finish(root=catalog),
        'fields': expectations,
        'need': {'present': need != 'absent',
                 'value': None if need == 'absent' else need},
    }


def W(page=0, rect=(10, 20, 190, 60), ap='none', states=None, as_state=None, extra=b''):
    widget = {'page': page, 'rect': rect, 'ap': ap, 'extra': extra}
    if states is not None:
        widget['ap'] = ('dict', list(states))
    if as_state is not None:
        widget['as'] = as_state
    return widget


def F(t=None, ft='Tx', flags=None, v=None, dv=None, da=None, q=None, maxlen=None,
      opt=None, widget=None, widgets=None, kids=None, extra=b'', a=False, aa=False):
    spec = {'t': t}
    for key, value in (('ft', ft), ('flags', flags), ('v', v), ('dv', dv), ('da', da),
                       ('q', q), ('maxlen', maxlen), ('opt', opt)):
        if value is not None:
            spec[key] = value
    if widget is not None:
        spec['widget'] = widget
    if widgets:
        spec['widgets'] = widgets
    if kids:
        spec['kids'] = kids
    if extra:
        spec['extra'] = extra
    if a:
        spec['a'] = True
    if aa:
        spec['aa'] = True
    return spec


TEXT_RECT = (10, 20, 190, 60)
BOX_RECT = (10, 20, 30, 40)
RADIO_A = (10, 20, 30, 40)
RADIO_B = (40, 20, 60, 40)
LIST_RECT = (10, 10, 190, 110)
COMBO_RECT = (10, 60, 190, 90)


def deep_chain(depth):
    node = F(t='l%d' % depth, ft='Tx', widget=W(page=0, rect=TEXT_RECT))
    for level in range(depth - 1, 0, -1):
        node = F(t='l%d' % level, kids=[node])
    return node


def basic_text(name='person.name', value=None, widget=None, **kw):
    spec = F(t=name, ft='Tx', widget=widget or W(), **kw)
    if value is not None:
        spec['v'] = ('text', value)
    return spec


def build_mixed_batch():
    fields = [
        F(t='person', ft='Tx', v=('text', 'inherited'), da='/Helv 9 Tf 0 g', q=0,
          kids=[F(t='given', widget=W(page=0, rect=TEXT_RECT)),
                F(t='family', dv=('text', 'Default'), widget=W(page=0, rect=(10, 65, 190, 100)))]),
        F(t='initial', ft='Tx', maxlen=9, v=('text', 'seed'), widget=W(page=1, rect=TEXT_RECT)),
        F(t='agree', ft='Btn', v=('name', 'Off'),
          widget=W(page=1, rect=BOX_RECT, states=['Yes'], as_state='Off')),
        F(t='news', ft='Btn', v=('name', 'Yes'),
          widget=W(page=1, rect=(10, 50, 30, 70), states=['Yes'], as_state='Yes')),
        F(t='color', ft='Btn', flags=BUTTON_FLAGS['radio'], v=('name', 'Green'),
          widgets=[W(page=2, rect=RADIO_A, states=['Red'], as_state='Off'),
                   W(page=2, rect=RADIO_B, states=['Green'], as_state='Green')]),
        F(t='size', ft='Ch', opt=['Small', ('medium', 'Medium'), ('large', 'Large')],
          v=('text', 'medium'), widget=W(page=2, rect=(10, 70, 190, 110))),
    ]
    return build_form(pages=3, fields=fields, need=True, doc_id=b'0018')


def build_choice_multi():
    return build_form(fields=[
        F(t='tags', ft='Ch', flags=CHOICE_FLAGS['multiselect'],
          opt=['Alpha', 'Beta', 'Gamma', 'Delta'], v=('list', ['Alpha', 'Delta']),
          widget=W(page=0, rect=LIST_RECT)),
    ], doc_id=b'0017')


def build_choice_label():
    return build_form(fields=[
        F(t='country', ft='Ch', flags=CHOICE_FLAGS['combo'],
          opt=[('US', 'United States'), ('CA', 'Canada'), ('MX', 'Mexico')],
          v=('text', 'CA'), widget=W(page=0, rect=COMBO_RECT)),
    ], doc_id=b'0019')


def build_three_pages():
    return build_form(pages=3, fields=[
        F(t='stamp', ft='Tx', v=('text', 'draft'),
          widgets=[W(page=0, rect=TEXT_RECT), W(page=1, rect=TEXT_RECT), W(page=2, rect=TEXT_RECT)]),
        F(t='note', ft='Tx', widget=W(page=1, rect=(10, 70, 190, 105))),
    ], doc_id=b'0005')


def build_merged_kids():
    return build_form(fields=[
        F(t='alias', ft='Tx', v=('text', 'seed'),
          widget=W(page=0, rect=TEXT_RECT),
          widgets=[W(page=1, rect=TEXT_RECT), W(page=2, rect=TEXT_RECT)]),
    ], pages=3, doc_id=b'0007')


def build_duplicate_partials():
    return build_form(fields=[
        F(t='left', ft='Tx', kids=[F(t='x', widget=W(page=0, rect=TEXT_RECT))]),
        F(t='right', ft='Tx', kids=[F(t='x', widget=W(page=0, rect=(10, 65, 190, 100)))]),
    ], doc_id=b'0022')


def build_deep_nesting():
    return build_form(fields=[deep_chain(12)], doc_id=b'0021')


def manual_doc(objects, doc_id, root=1):
    doc = Doc(doc_id)
    for index in sorted(objects):
        doc.put(index, objects[index])
    return {'data': doc.finish(root=root), 'fields': [],
            'need': {'present': False, 'value': None}}


def build_cycle():
    return manual_doc({
        1: b'<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [10 0 R] >> >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] >>',
        10: b'<< /T (a) /FT /Tx /Kids [11 0 R] >>',
        11: b'<< /T (b) /Parent 10 0 R /Kids [10 0 R] >>',
    }, b'0068')


def build_shared_child():
    return manual_doc({
        1: b'<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [10 0 R 11 0 R] >> >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] >>',
        10: b'<< /T (a) /FT /Tx /Kids [12 0 R] >>',
        11: b'<< /T (b) /FT /Tx /Kids [12 0 R] >>',
        12: b'<< /T (c) /Parent 10 0 R >>',
    }, b'0069')


def build_mixed_kids():
    return manual_doc({
        1: b'<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [10 0 R] >> >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] /Annots [12 0 R] >>',
        10: b'<< /T (a) /FT /Tx /Kids [11 0 R 12 0 R] >>',
        11: b'<< /T (b) /Parent 10 0 R >>',
        12: b'<< /Subtype /Widget /Parent 10 0 R /Rect [10 10 50 30] >>',
    }, b'0070')


def build_parent_mismatch():
    return manual_doc({
        1: b'<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [10 0 R] >> >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] >>',
        10: b'<< /T (a) /FT /Tx /Kids [11 0 R] >>',
        11: b'<< /T (b) /FT /Tx /Parent 12 0 R >>',
        12: b'<< /Type /XObject /Subtype /Form /BBox [0 0 1 1] >>',
    }, b'0071')


def build_duplicate_name():
    return manual_doc({
        1: b'<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [10 0 R 11 0 R] >> >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] >>',
        10: b'<< /T (dup) /FT /Tx >>',
        11: b'<< /T (dup) /FT /Tx >>',
    }, b'0072')


def build_bad_rect():
    return manual_doc({
        1: b'<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [10 0 R] >> >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] /Annots [11 0 R] >>',
        10: b'<< /T (w) /FT /Tx /Kids [11 0 R] >>',
        11: b'<< /Subtype /Widget /Parent 10 0 R /Rect [10 10 10 30] >>',
    }, b'0073')


def build_multi_page_annot():
    return manual_doc({
        1: b'<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [10 0 R] >> >>',
        2: b'<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] /Annots [11 0 R] >>',
        4: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] /Annots [11 0 R] >>',
        10: b'<< /T (w) /FT /Tx /Kids [11 0 R] >>',
        11: b'<< /Subtype /Widget /Parent 10 0 R /Rect [10 10 50 30] >>',
    }, b'0074')


def build_depth_limit():
    objects = {
        1: b'<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [10 0 R] >> >>',
        2: b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        3: b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] >>',
    }
    last = 75
    for index in range(10, last + 1):
        body = b'<< /T (n) /FT /Tx'
        if index > 10:
            body += b' /Parent %d 0 R' % (index - 1)
        if index < last:
            body += b' /Kids [%d 0 R]' % (index + 1)
        body += b' >>'
        objects[index] = body
    return manual_doc(objects, b'0075')


FILES = [
    {
        'id': '01', 'slug': 'text-ascii-basic', 'category': 'text/basic',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0001'),
        'changes': [('person.name', ['Alice'])],
        'notes': 'Single merged text widget, no existing appearance, ASCII value without a host font.',
    },
    {
        'id': '02', 'slug': 'text-inherit-two-widgets', 'category': 'text/inheritance',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='person', ft='Tx', flags=0, maxlen=12, v=('text', 'inherited'),
              dv=('text', 'default'), da='/Helv 10 Tf 0 g', q=1,
              kids=[F(t='name', widgets=[W(page=0, rect=TEXT_RECT), W(page=1, rect=TEXT_RECT)])]),
        ], pages=2, doc_id=b'0002'),
        'changes': [('person.name', ['Ada Lovelace'])],
        'notes': 'Type, flags, MaxLen, value, default, DA and Q inherited from the parent; two widgets on two pages.',
    },
    {
        'id': '03', 'slug': 'text-align-right', 'category': 'text/justification',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            basic_text(name='aligned', q=2),
        ], doc_id=b'0003'),
        'changes': [('aligned', ['right'])],
        'notes': 'Q=2 justification drives right-aligned appearance placement.',
    },
    {
        'id': '04', 'slug': 'text-existing-appearance', 'category': 'text/appearance',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='kept', ft='Tx', v=('text', 'old'),
              widget=W(page=0, rect=TEXT_RECT, ap='stream', extra=b'/F 4 /NM (kept-widget)')),
        ], doc_id=b'0004'),
        'changes': [('kept', ['replaced'])],
        'notes': 'Existing normal appearance stream and unrelated widget dictionary entries survive the replacement.',
    },
    {
        'id': '05', 'slug': 'text-three-pages', 'category': 'widget/multipage',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': build_three_pages,
        'changes': [('stamp', ['final'])],
        'notes': 'One field with three widgets mapped to three distinct pages; an unedited second field stays intact.',
    },
    {
        'id': '06', 'slug': 'text-detached-widget', 'category': 'widget/detached',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='orphan', ft='Tx', widget=W(page=None, rect=TEXT_RECT)),
            F(t='anchored', ft='Tx', widget=W(page=0, rect=(10, 65, 190, 100))),
        ], doc_id=b'0006'),
        'changes': [('orphan', ['detached'])],
        'notes': 'Widget absent from every page Annots list reports SIZE_MAX and is still writable.',
    },
    {
        'id': '07', 'slug': 'text-merged-and-kids', 'category': 'widget/merged',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': build_merged_kids,
        'changes': [('alias', ['three'])],
        'notes': 'The field dictionary is itself a widget and also owns two kid widgets.',
    },
    {
        'id': '08', 'slug': 'text-clear', 'category': 'text/empty',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[basic_text(value='filled')], doc_id=b'0008'),
        'changes': [('person.name', [''])],
        'notes': 'An empty value clears the field and leaves no text ink in the interior.',
    },
    {
        'id': '09', 'slug': 'text-spaces', 'category': 'text/blank',
        'expect': 'accept', 'op': 'write', 'font': 1,
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0009'),
        'changes': [('person.name', ['   '])],
        'notes': 'Blank glyph outlines are permitted for spaces and paint no ink.',
    },
    {
        'id': '10', 'slug': 'text-long-shrink', 'category': 'text/fit',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[basic_text(widget=W(rect=(10, 20, 70, 45)))], doc_id=b'0010'),
        'changes': [('person.name', ['A much longer single line value'])],
        'notes': 'A narrow widget shrinks the font instead of overflowing or clipping outside the box.',
    },
    {
        'id': '11', 'slug': 'text-unicode', 'category': 'text/unicode',
        'expect': 'accept', 'op': 'write', 'font': 1,
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0011'),
        'changes': [('person.name', ['\u7532\u4e59\U0001F600'])],
        'notes': 'CJK and non-BMP scalars are shaped once into outlines that reopen without the borrowed font.',
    },
    {
        'id': '12', 'slug': 'text-utf16-name', 'category': 'text/name-encoding',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='person', ft='Tx', kids=[F(t='na\u00efve', widget=W())]),
        ], doc_id=b'0012'),
        'changes': [('person.na\u00efve', ['encoded'])],
        'notes': 'A non-ASCII partial name is written as a UTF-16BE text string and addressed by its UTF-8 qualified name.',
    },
    {
        'id': '13', 'slug': 'checkbox-basic', 'category': 'checkbox/basic',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='check0', ft='Btn', v=('name', 'Off'), widget=W(page=0, rect=BOX_RECT, states=['Yes'], as_state='Off')),
            F(t='check1', ft='Btn', v=('name', 'Off'), widget=W(page=0, rect=(10, 50, 30, 70), states=['Yes'], as_state='Off')),
            F(t='check2', ft='Btn', v=('name', 'Yes'), widget=W(page=0, rect=(10, 80, 30, 100), states=['Yes'], as_state='Yes')),
        ], doc_id=b'0013'),
        'changes': [('check0', ['Yes']), ('check1', ['Yes'])],
        'notes': 'Two checkboxes turn on while an unedited third keeps its checked appearance.',
    },
    {
        'id': '14', 'slug': 'checkbox-off', 'category': 'checkbox/off',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='check0', ft='Btn', v=('name', 'Yes'), widget=W(page=0, rect=BOX_RECT, states=['Yes'], as_state='Yes')),
        ], doc_id=b'0014'),
        'changes': [('check0', ['Off'])],
        'notes': 'Turning a checked box off selects the Off appearance and removes the check ink.',
    },
    {
        'id': '15', 'slug': 'checkbox-existing-dict', 'category': 'checkbox/appearance',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='check0', ft='Btn', v=('name', 'Off'),
              widget=W(page=0, rect=BOX_RECT, states=['Yes'], as_state='Off', extra=b'/F 4')),
        ], doc_id=b'0015'),
        'changes': [('check0', ['Yes'])],
        'notes': 'Existing named normal appearances are replaced by Off and on-state streams with a matching AS.',
    },
    {
        'id': '16', 'slug': 'radio-basic', 'category': 'radio/basic',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='choice', ft='Btn', flags=BUTTON_FLAGS['radio'], v=('name', 'Off'),
              widgets=[W(page=0, rect=RADIO_A, states=['Red'], as_state='Off'),
                       W(page=0, rect=RADIO_B, states=['Blue'], as_state='Off')]),
        ], doc_id=b'0016'),
        'changes': [('choice', ['Blue'])],
        'notes': 'Two widgets with distinct export names select exactly one on state.',
    },
    {
        'id': '17', 'slug': 'radio-unison', 'category': 'radio/unison',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='choice', ft='Btn', flags=BUTTON_FLAGS['radio'] | BUTTON_FLAGS['unison'],
              v=('name', 'Off'),
              widgets=[W(page=0, rect=RADIO_A, states=['Red'], as_state='Off'),
                       W(page=0, rect=RADIO_B, states=['Red'], as_state='Off')]),
        ], doc_id=b'0017'),
        'changes': [('choice', ['Red'])],
        'notes': 'RadiosInUnison permits two widgets that share one export name; both select and both AS values match.',
    },
    {
        'id': '18', 'slug': 'radio-two-pages', 'category': 'radio/multipage',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(pages=2, fields=[
            F(t='choice', ft='Btn', flags=BUTTON_FLAGS['radio'], v=('name', 'Off'),
              widgets=[W(page=0, rect=RADIO_A, states=['Left'], as_state='Off'),
                       W(page=1, rect=RADIO_A, states=['Right'], as_state='Off')]),
        ], doc_id=b'0018'),
        'changes': [('choice', ['Right'])],
        'notes': 'A radio group split across two pages keeps one selected widget per page mapping.',
    },
    {
        'id': '19', 'slug': 'radio-off', 'category': 'radio/off',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='choice', ft='Btn', flags=BUTTON_FLAGS['radio'], v=('name', 'Red'),
              widgets=[W(page=0, rect=RADIO_A, states=['Red'], as_state='Red'),
                       W(page=0, rect=RADIO_B, states=['Blue'], as_state='Off')]),
        ], doc_id=b'0019'),
        'changes': [('choice', ['Off'])],
        'notes': 'Without NoToggleToOff the group can be cleared, and every widget selects Off.',
    },
    {
        'id': '20', 'slug': 'choice-list', 'category': 'choice/list',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='pet', ft='Ch', v=('text', 'cat'),
              opt=[('cat', 'Cat'), ('dog', 'Dog'), 'fish'], widget=W(page=0, rect=LIST_RECT)),
        ], doc_id=b'0020'),
        'changes': [('pet', ['fish'])],
        'notes': 'A single-selection list writes V, the option index I and the selected label appearance.',
    },
    {
        'id': '21', 'slug': 'choice-multi', 'category': 'choice/multiselect',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': build_choice_multi,
        'changes': [('tags', ['Delta', 'Beta'])],
        'notes': 'Multi-select values are written in Opt order with indexes and one label row per selection.',
    },
    {
        'id': '22', 'slug': 'choice-combo', 'category': 'choice/combo',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='city', ft='Ch', flags=CHOICE_FLAGS['combo'], v=('text', 'Oslo'),
              opt=['Oslo', 'Rome', 'Kyiv'], widget=W(page=0, rect=COMBO_RECT)),
        ], doc_id=b'0022'),
        'changes': [('city', ['Rome'])],
        'notes': 'A non-editable combo box renders its single selection as one text line.',
    },
    {
        'id': '23', 'slug': 'choice-labels', 'category': 'choice/labels',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': build_choice_label,
        'changes': [('country', ['Mexico'])],
        'notes': 'Export value and display label differ; the appearance must show the label, not the export value.',
    },
    {
        'id': '24', 'slug': 'mixed-batch', 'category': 'mixed/batch',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': build_mixed_batch,
        'changes': [('person.given', ['Grace']), ('person.family', ['Hopper']),
                    ('agree', ['Yes']), ('color', ['Red']), ('size', ['large']),
                    ('initial', ['rewritten'])],
        'notes': 'Six mixed-kind changes in one atomic call across three pages with NeedAppearances already true.',
    },
    {
        'id': '25', 'slug': 'needappearances-true', 'category': 'need-appearances/true',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(need=True, fields=[
            F(t='edited', ft='Tx', v=('text', 'one'), widget=W(page=0, rect=TEXT_RECT)),
            F(t='untouched', ft='Tx', v=('text', 'two'),
              widget=W(page=0, rect=(10, 65, 190, 100), ap='stream')),
        ], doc_id=b'0025'),
        'changes': [('edited', ['changed'])],
        'notes': 'A partial edit preserves the original NeedAppearances request and the unedited widget appearance stream.',
    },
    {
        'id': '26', 'slug': 'needappearances-false', 'category': 'need-appearances/false',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(need=False, fields=[
            F(t='edited', ft='Tx', v=('text', 'one'), widget=W(page=0, rect=TEXT_RECT)),
        ], doc_id=b'0026'),
        'changes': [('edited', ['changed'])],
        'notes': 'An explicit false NeedAppearances stays false; the edit must not turn it into a request.',
    },
    {
        'id': '27', 'slug': 'needappearances-absent', 'category': 'need-appearances/absent',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='edited', ft='Tx', v=('text', 'one'), widget=W(page=0, rect=TEXT_RECT)),
        ], doc_id=b'0027'),
        'changes': [('edited', ['changed'])],
        'notes': 'An absent NeedAppearances entry stays absent after a partial edit.',
    },
    {
        'id': '28', 'slug': 'acroform-direct', 'category': 'structure/direct-acroform',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(acroform_direct=True, fields=[
            F(t='inline', ft='Tx', v=('text', 'before'), widget=W(page=0, rect=TEXT_RECT)),
        ], doc_id=b'0028'),
        'changes': [('inline', ['after'])],
        'notes': 'The AcroForm dictionary is direct in the catalog; the catalog is rewritten with the new form.',
    },
    {
        'id': '29', 'slug': 'extra-annots', 'category': 'widget/non-widget-annots',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='field', ft='Tx', widget=W(page=0, rect=(10, 65, 190, 100))),
        ], extra_annots=[(0, b'<< /Type /Annot /Subtype /Link /Rect [10 10 40 20] /Border [0 0 0] >>'),
                         (0, b'<< /Type /Annot /Subtype /Text /Rect [45 10 60 25] /Contents (note) >>')],
         doc_id=b'0029'),
        'changes': [('field', ['value'])],
        'notes': 'Non-widget annotations on the same page keep their order and are untouched by the form edit.',
    },
    {
        'id': '30', 'slug': 'deep-nesting', 'category': 'structure/deep-nesting',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': build_deep_nesting,
        'changes': [('l1.l2.l3.l4.l5.l6.l7.l8.l9.l10.l11.l12', ['leaf'])],
        'notes': 'Twelve inherited levels below the 64 level cap produce a dotted qualified name.',
    },
    {
        'id': '31', 'slug': 'duplicate-partials', 'category': 'structure/qualified-names',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': build_duplicate_partials,
        'changes': [('left.x', ['one']), ('right.x', ['two'])],
        'notes': 'Equal partial names under different parents stay distinct qualified names in one call.',
    },
    {
        'id': '32', 'slug': 'zero-change', 'category': 'structure/zero-change',
        'expect': 'accept', 'op': 'write-empty', 'font': 0,
        'build': lambda: build_form(fields=[basic_text(value='unchanged')], doc_id=b'0032'),
        'changes': [],
        'notes': 'A zero-change write returns an independent byte-identical copy of the input.',
    },
    {
        'id': '33', 'slug': 'maxlen-scalars', 'category': 'text/maxlen',
        'expect': 'accept', 'op': 'write', 'font': 1,
        'build': lambda: build_form(fields=[basic_text(maxlen=8)], doc_id=b'0033'),
        'changes': [('person.name', ['\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b'])],
        'notes': 'MaxLen counts Unicode scalars, so eight CJK scalars fit an eight-scalar limit.',
    },
    {
        'id': '34', 'slug': 'no-acroform', 'category': 'structure/no-form',
        'expect': 'empty', 'op': 'read', 'font': 0,
        'build': lambda: build_form(pages=1, fields=[], with_form=False, doc_id=b'0034'),
        'changes': [],
        'notes': 'A PDF without AcroForm reads as an empty successful snapshot.',
    },
    {
        'id': '35', 'slug': 'action-flag-isolated', 'category': 'structure/action-flag',
        'expect': 'accept', 'op': 'write', 'font': 0,
        'build': lambda: build_form(fields=[
            F(t='plain', ft='Tx', widget=W(page=0, rect=TEXT_RECT)),
            F(t='scripted', ft='Tx', widget=W(page=0, rect=(10, 65, 190, 100)), aa=True),
        ], doc_id=b'0035'),
        'changes': [('plain', ['editable'])],
        'notes': 'A field with an additional action raises the actions issue for itself only and is not edited.',
    },
    {
        'id': '36', 'slug': 'reject-readonly', 'category': 'reject/readonly',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_ARGUMENT',
        'build': lambda: build_form(fields=[basic_text(flags=TEXT_FLAGS['readonly'])], doc_id=b'0036'),
        'changes': [('person.name', ['x'])],
        'notes': 'Read-only fields refuse every change and leave the input untouched.',
    },
    {
        'id': '37', 'slug': 'reject-required-empty', 'category': 'reject/required',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_ARGUMENT',
        'build': lambda: build_form(fields=[basic_text(flags=TEXT_FLAGS['required'])], doc_id=b'0037'),
        'changes': [('person.name', [''])],
        'notes': 'A required field rejects an empty value.',
    },
    {
        'id': '38', 'slug': 'reject-maxlen', 'category': 'reject/maxlen',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_ARGUMENT',
        'build': lambda: build_form(fields=[basic_text(maxlen=4)], doc_id=b'0038'),
        'changes': [('person.name', ['ABCDE'])],
        'notes': 'More scalars than MaxLen rejects instead of truncating.',
    },
    {
        'id': '39', 'slug': 'reject-multiline', 'category': 'reject/multiline',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[basic_text(flags=TEXT_FLAGS['multiline'])], doc_id=b'0039'),
        'changes': [('person.name', ['x'])],
        'notes': 'Multiline text has no declared appearance layout and is refused.',
    },
    {
        'id': '40', 'slug': 'reject-password', 'category': 'reject/password',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[basic_text(flags=TEXT_FLAGS['password'])], doc_id=b'0040'),
        'changes': [('person.name', ['x'])],
        'notes': 'Password masking is not implemented.',
    },
    {
        'id': '41', 'slug': 'reject-comb', 'category': 'reject/comb',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[basic_text(flags=TEXT_FLAGS['comb'], maxlen=6)], doc_id=b'0041'),
        'changes': [('person.name', ['x'])],
        'notes': 'Comb cell layout needs character cells that are not generated.',
    },
    {
        'id': '42', 'slug': 'reject-richtext', 'category': 'reject/richtext',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[basic_text(flags=TEXT_FLAGS['richtext'])], doc_id=b'0042'),
        'changes': [('person.name', ['x'])],
        'notes': 'Rich text runs beyond a single-line appearance.',
    },
    {
        'id': '43', 'slug': 'reject-fileselect', 'category': 'reject/fileselect',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[basic_text(flags=TEXT_FLAGS['fileselect'])], doc_id=b'0043'),
        'changes': [('person.name', ['x'])],
        'notes': 'File-select fields are not text values.',
    },
    {
        'id': '44', 'slug': 'reject-editable-combo', 'category': 'reject/editable-combo',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[
            F(t='combo', ft='Ch', flags=CHOICE_FLAGS['combo'] | CHOICE_FLAGS['edit'],
              opt=['One', 'Two'], widget=W(page=0, rect=COMBO_RECT)),
        ], doc_id=b'0044'),
        'changes': [('combo', ['One'])],
        'notes': 'An editable combo may carry arbitrary text outside Opt and is refused.',
    },
    {
        'id': '45', 'slug': 'reject-multiselect-combo', 'category': 'reject/multiselect-combo',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[
            F(t='combo', ft='Ch', flags=CHOICE_FLAGS['combo'] | CHOICE_FLAGS['multiselect'],
              opt=['One', 'Two'], widget=W(page=0, rect=COMBO_RECT)),
        ], doc_id=b'0045'),
        'changes': [('combo', ['One'])],
        'notes': 'A multi-select combo box has no declared appearance layout.',
    },
    {
        'id': '46', 'slug': 'reject-rotation', 'category': 'reject/rotation',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[
            basic_text(widget=W(rect=TEXT_RECT, extra=b'/MK << /R 90 >>')),
        ], doc_id=b'0046'),
        'changes': [('person.name', ['x'])],
        'notes': 'Rotated widgets need a rotated appearance matrix that is not generated.',
    },
    {
        'id': '47', 'slug': 'reject-actions', 'category': 'reject/actions',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[
            F(t='scripted', ft='Tx', widget=W(page=0, rect=TEXT_RECT), aa=True),
        ], doc_id=b'0047'),
        'changes': [('scripted', ['x'])],
        'notes': 'Fields with additional actions are refused and never executed.',
    },
    {
        'id': '48', 'slug': 'reject-xfa', 'category': 'reject/xfa',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[basic_text()], acro_extra=b'/XFA (record only)', doc_id=b'0048'),
        'changes': [('person.name', ['x'])],
        'notes': 'An XFA payload marks the form unsupported for writing.',
    },
    {
        'id': '49', 'slug': 'reject-permissions', 'category': 'reject/permissions',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_FORMAT',
        'build': lambda: build_form(fields=[basic_text()],
                                    catalog_extra=b'/Perms << /DocMDP << /Type /Sig >> >>',
                                    doc_id=b'0049'),
        'changes': [('person.name', ['x'])],
        'notes': 'Catalog permission constraints block writing before any object is appended.',
    },
    {
        'id': '50', 'slug': 'reject-radio-duplicate', 'category': 'reject/radio-duplicate',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[
            F(t='choice', ft='Btn', flags=BUTTON_FLAGS['radio'], v=('name', 'Off'),
              widgets=[W(page=0, rect=RADIO_A, states=['Red'], as_state='Off'),
                       W(page=0, rect=RADIO_B, states=['Red'], as_state='Off')]),
        ], doc_id=b'0050'),
        'changes': [('choice', ['Red'])],
        'notes': 'Duplicate radio export names without RadiosInUnison are ambiguous and refused.',
    },
    {
        'id': '51', 'slug': 'reject-radio-notoggle', 'category': 'reject/radio-notoggle',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_ARGUMENT',
        'build': lambda: build_form(fields=[
            F(t='choice', ft='Btn', flags=BUTTON_FLAGS['radio'] | BUTTON_FLAGS['notoggle'],
              v=('name', 'Red'),
              widgets=[W(page=0, rect=RADIO_A, states=['Red'], as_state='Red'),
                       W(page=0, rect=RADIO_B, states=['Blue'], as_state='Off')]),
        ], doc_id=b'0051'),
        'changes': [('choice', ['Off'])],
        'notes': 'NoToggleToOff forbids clearing every widget of the group.',
    },
    {
        'id': '52', 'slug': 'reject-signature', 'category': 'reject/signature',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[F(t='sig', ft='Sig', widget=W(rect=TEXT_RECT))], doc_id=b'0052'),
        'changes': [('sig', ['x'])],
        'notes': 'Signature fields are enumerable but never written.',
    },
    {
        'id': '53', 'slug': 'reject-pushbutton', 'category': 'reject/pushbutton',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[
            F(t='push', ft='Btn', flags=BUTTON_FLAGS['push'], widget=W(rect=TEXT_RECT)),
        ], doc_id=b'0053'),
        'changes': [('push', ['x'])],
        'notes': 'Pushbuttons carry no value and are refused.',
    },
    {
        'id': '54', 'slug': 'reject-unknown-ft', 'category': 'reject/unknown-type',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[F(t='odd', ft='Foo', widget=W(rect=TEXT_RECT))], doc_id=b'0054'),
        'changes': [('odd', ['x'])],
        'notes': 'Unknown field types enumerate but never write.',
    },
    {
        'id': '55', 'slug': 'reject-choice-duplicate-exports', 'category': 'reject/choice-duplicate',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_FORMAT',
        'build': lambda: build_form(fields=[
            F(t='dup', ft='Ch', opt=['A', ('A', 'Second')], v=('text', 'A'),
              widget=W(page=0, rect=LIST_RECT)),
        ], doc_id=b'0055'),
        'changes': [('dup', ['A'])],
        'notes': 'Duplicate choice export values make the index ambiguous and are refused.',
    },
    {
        'id': '56', 'slug': 'reject-choice-absent', 'category': 'reject/choice-absent',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_ARGUMENT',
        'build': lambda: build_form(fields=[
            F(t='pick', ft='Ch', opt=['A', 'B'], widget=W(page=0, rect=LIST_RECT)),
        ], doc_id=b'0056'),
        'changes': [('pick', ['Z'])],
        'notes': 'A value outside Opt is rejected before any appearance is written.',
    },
    {
        'id': '57', 'slug': 'reject-duplicate-change', 'category': 'reject/duplicate-change',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_ARGUMENT',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0057'),
        'changes': [('person.name', ['a']), ('person.name', ['b'])],
        'notes': 'The same field changed twice in one batch is rejected.',
    },
    {
        'id': '58', 'slug': 'reject-missing-field', 'category': 'reject/missing-field',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_ARGUMENT',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0058'),
        'changes': [('absent', ['x'])],
        'notes': 'A change naming an absent field is rejected.',
    },
    {
        'id': '59', 'slug': 'reject-invalid-utf8', 'category': 'reject/encoding',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_ENCODING',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0059'),
        'changes': [('person.name', [b'\xff'])],
        'notes': 'Invalid UTF-8 in a value reports an encoding error.',
    },
    {
        'id': '60', 'slug': 'reject-control-char', 'category': 'reject/control-character',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_ARGUMENT',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0060'),
        'changes': [('person.name', ['A\tB'])],
        'notes': 'Control characters cannot be laid out in a single-line appearance.',
    },
    {
        'id': '61', 'slug': 'reject-missing-glyph', 'category': 'reject/missing-glyph',
        'expect': 'reject', 'op': 'reject', 'font': 1, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0061'),
        'changes': [('person.name', ['\ue000'])],
        'notes': 'A scalar with no glyph in the borrowed font is refused rather than painted as notdef.',
    },
    {
        'id': '62', 'slug': 'reject-bidi', 'category': 'reject/bidi',
        'expect': 'reject', 'op': 'reject', 'font': 1, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0062'),
        'changes': [('person.name', ['A \u05d0'])],
        'notes': 'Bidirectional runs need a layout the appearance generator does not provide.',
    },
    {
        'id': '63', 'slug': 'reject-outline-only', 'category': 'reject/empty-outline',
        'expect': 'reject', 'op': 'reject', 'font': 2, 'status': 'EXR_UNSUPPORTED',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0063'),
        'changes': [('person.name', ['A'])],
        'notes': 'A font whose visible glyphs have no outlines cannot produce an appearance.',
    },
    {
        'id': '64', 'slug': 'reject-bad-justification', 'category': 'reject/justification',
        'expect': 'reject', 'op': 'reject', 'font': 0, 'status': 'EXR_FORMAT',
        'build': lambda: build_form(fields=[basic_text(q=5)], doc_id=b'0064'),
        'changes': [('person.name', ['x'])],
        'notes': 'A justification outside 0..2 is malformed and refused before writing.',
    },
    {
        'id': '65', 'slug': 'cancel-entry', 'category': 'cancel/entry',
        'expect': 'cancel', 'op': 'cancel-entry', 'font': 0, 'status': 'EXR_CANCELLED',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0065'),
        'changes': [('person.name', ['x'])],
        'notes': 'A cancel flag observed at entry returns CANCELLED with cleared outputs.',
    },
    {
        'id': '66', 'slug': 'cancel-final', 'category': 'cancel/export-completion',
        'expect': 'cancel', 'op': 'cancel-final', 'font': 0, 'status': 'EXR_CANCELLED',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0066'),
        'changes': [('person.name', ['x'])],
        'notes': 'Cancelling when export progress completes discards the whole revision.',
    },
    {
        'id': '67', 'slug': 'cancel-shape', 'category': 'cancel/shaping',
        'expect': 'cancel', 'op': 'cancel-shape', 'font': 1, 'status': 'EXR_CANCELLED',
        'build': lambda: build_form(fields=[basic_text()], doc_id=b'0067'),
        'changes': [('person.name', ['shaped'])],
        'notes': 'Cancelling during shaping reports CANCELLED and preserves the input.',
    },
    {
        'id': '68', 'slug': 'read-cycle', 'category': 'read/cycle',
        'expect': 'read-fail', 'op': 'read-fail', 'font': 0, 'status': 'EXR_FORMAT',
        'build': build_cycle, 'changes': [],
        'notes': 'A field that contains itself through Kids is rejected atomically.',
    },
    {
        'id': '69', 'slug': 'read-shared-child', 'category': 'read/shared-child',
        'expect': 'read-fail', 'op': 'read-fail', 'font': 0, 'status': 'EXR_FORMAT',
        'build': build_shared_child, 'changes': [],
        'notes': 'One child reached from two parents is rejected as a shared child.',
    },
    {
        'id': '70', 'slug': 'read-mixed-kids', 'category': 'read/mixed-kids',
        'expect': 'read-fail', 'op': 'read-fail', 'font': 0, 'status': 'EXR_FORMAT',
        'build': build_mixed_kids, 'changes': [],
        'notes': 'A Kids array holding both fields and widgets is malformed.',
    },
    {
        'id': '71', 'slug': 'read-parent-mismatch', 'category': 'read/parent-mismatch',
        'expect': 'read-fail', 'op': 'read-fail', 'font': 0, 'status': 'EXR_FORMAT',
        'build': build_parent_mismatch, 'changes': [],
        'notes': 'A Parent entry that disagrees with the field tree is rejected.',
    },
    {
        'id': '72', 'slug': 'read-duplicate-name', 'category': 'read/duplicate-name',
        'expect': 'read-fail', 'op': 'read-fail', 'font': 0, 'status': 'EXR_FORMAT',
        'build': build_duplicate_name, 'changes': [],
        'notes': 'Two fields with the same qualified name are ambiguous.',
    },
    {
        'id': '73', 'slug': 'read-bad-rect', 'category': 'read/bad-rect',
        'expect': 'read-fail', 'op': 'read-fail', 'font': 0, 'status': 'EXR_FORMAT',
        'build': build_bad_rect, 'changes': [],
        'notes': 'A widget rectangle without positive area is rejected.',
    },
    {
        'id': '74', 'slug': 'read-multi-page-annot', 'category': 'read/multi-page-annot',
        'expect': 'read-fail', 'op': 'read-fail', 'font': 0, 'status': 'EXR_FORMAT',
        'build': build_multi_page_annot, 'changes': [],
        'notes': 'One widget listed on two pages has no unique page mapping.',
    },
    {
        'id': '75', 'slug': 'read-depth-limit', 'category': 'read/depth-limit',
        'expect': 'read-fail', 'op': 'read-fail', 'font': 0, 'status': 'EXR_LIMIT',
        'build': build_depth_limit, 'changes': [],
        'notes': 'Sixty-six field levels exceed the 64 level tree cap.',
    },
]

FONT_ROLES = {
    0: 'none',
    1: 'tests/fixtures/fonts/fallback.ttf',
    2: 'tests/fixtures/fonts/cbdt.ttf',
}


def base_name(entry):
    return '%s-%s.pdf' % (entry['id'], entry['slug'])


def hex_of(value):
    raw = value if isinstance(value, bytes) else value.encode('utf-8')
    return raw.hex()


def plan_text(files):
    lines = []
    for entry in files:
        lines.append('\t'.join(['P', entry['id'], base_name(entry), entry['op'], str(entry['font'])]))
        for field, values in entry['changes']:
            cells = ['C', entry['id'], hex_of(field)]
            cells.extend(hex_of(value) for value in values)
            lines.append('\t'.join(cells))
    return '\n'.join(lines) + '\n'


def change_record(entry):
    out = []
    for field, values in entry['changes']:
        encoded = []
        for value in values:
            if isinstance(value, bytes):
                encoded.append({'hex': value.hex()})
            else:
                encoded.append(value)
        out.append({'field': field, 'values': encoded})
    return out


def validate_entry(entry, built):
    expect = entry['expect']
    op = entry['op']
    if expect in ('accept', 'empty'):
        if 'status' in entry:
            raise SystemExit('%s: accepted file must not declare a status' % entry['id'])
        if op == 'write' and not entry['changes']:
            raise SystemExit('%s: write requires at least one change' % entry['id'])
        if op == 'write-empty' and entry['changes']:
            raise SystemExit('%s: write-empty must not carry changes' % entry['id'])
    else:
        if not entry.get('status', '').startswith('EXR_'):
            raise SystemExit('%s: %s file needs an EXR status' % (entry['id'], expect))
        if not entry['changes'] and expect != 'read-fail':
            raise SystemExit('%s: %s file needs a change set' % (entry['id'], expect))
    names = set(field['name'] for field in built['fields'])
    if expect == 'accept':
        for field, _values in entry['changes']:
            if field not in names:
                raise SystemExit('%s: change names undeclared field %r' % (entry['id'], field))
    if entry['font'] not in FONT_ROLES:
        raise SystemExit('%s: unknown font role' % entry['id'])


def spec_record(entry, data, digest, built):
    record = {
        'id': entry['id'],
        'base': base_name(entry),
        'category': entry['category'],
        'expect': entry['expect'],
        'op': entry['op'],
        'font': entry['font'],
        'font_role': FONT_ROLES[entry['font']],
        'size': len(data),
        'sha256': digest,
        'need_appearances': built['need'],
        'changes': change_record(entry),
        'fields': built['fields'],
        'notes': entry['notes'],
    }
    if 'status' in entry:
        record['status'] = entry['status']
    return record


def main():
    parser = argparse.ArgumentParser(description='Generate the frozen AcroForm corpus')
    parser.add_argument('--out', required=True, type=pathlib.Path)
    arguments = parser.parse_args()
    out = arguments.out
    out.mkdir(parents=True, exist_ok=True)
    records = []
    digests = {}
    bases = set()
    for entry in FILES:
        built = entry['build']()
        data = built['data']
        if not data.startswith(b'%PDF-1.7'):
            raise SystemExit('%s: generated bytes lack a PDF header' % entry['id'])
        name = base_name(entry)
        if name in bases:
            raise SystemExit('%s: duplicate file name %s' % (entry['id'], name))
        bases.add(name)
        validate_entry(entry, built)
        (out / name).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        if digest in digests:
            raise SystemExit('%s: identical bytes to %s' % (entry['id'], digests[digest]))
        digests[digest] = entry['id']
        records.append(spec_record(entry, data, digest, built))
    if len(records) < 30:
        raise SystemExit('corpus holds %d files, below the 30 file gate' % len(records))
    plan = plan_text(FILES)
    (out / 'plan.tsv').write_text(plan, encoding='utf-8', newline='\n')
    spec = {
        'schema': 'exreader-acroform-corpus-spec/1',
        'generator': 'tests/acroform_corpus/generate.py',
        'page_size': [PAGE_W, PAGE_H],
        'font_roles': {str(key): value for key, value in FONT_ROLES.items()},
        'file_gate': 30,
        'file_count': len(records),
        'plan_sha256': hashlib.sha256(plan.encode('utf-8')).hexdigest(),
        'files': records,
    }
    (out / 'corpus-spec.json').write_text(
        json.dumps(spec, ensure_ascii=False, indent=1, sort_keys=False) + '\n',
        encoding='utf-8', newline='\n')
    manifest = {
        'schema': 'exreader-acroform-corpus-manifest/1',
        'file_count': len(records),
        'total_bytes': sum(record['size'] for record in records),
        'files': [{'id': record['id'], 'base': record['base'], 'category': record['category'],
                   'size': record['size'], 'sha256': record['sha256']} for record in records],
    }
    (out / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    summary = {
        'files': len(records),
        'accept': sum(1 for record in records if record['expect'] in ('accept', 'empty')),
        'reject': sum(1 for record in records if record['expect'] == 'reject'),
        'cancel': sum(1 for record in records if record['expect'] == 'cancel'),
        'read_fail': sum(1 for record in records if record['expect'] == 'read-fail'),
        'fields': sum(len(record['fields']) for record in records),
        'widgets': sum(len(field['widgets']) for record in records for field in record['fields']),
        'bytes': sum(record['size'] for record in records),
        'categories': len(set(record['category'] for record in records)),
    }
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


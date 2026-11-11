#!/usr/bin/env python3
"""Independent ZIP/OOXML audit of the requested Word formatting contract.

No EXReader imports. This checks the specified profile, not the entire ECMA schema.
Exit 1 means a failed check; warnings (unused/missing header) alone do not fail.
"""
import argparse
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import BadZipFile, ZipFile

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS = {'w': W, 'r': R}
ET.register_namespace('w', W)
ET.register_namespace('r', R)


def attr(node, name):
    return node.get('{%s}%s' % (W, name)) if node is not None else None


def context(node):
    return ET.tostring(node, encoding='unicode') if node is not None else '(missing XML element)'


class Package:
    def __init__(self, path):
        with ZipFile(path) as archive:
            if archive.testzip():
                raise ValueError('ZIP CRC failure')
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError('duplicate ZIP part names')
            self.parts = {n: archive.read(n) for n in names}
        self.xml = {n: ET.fromstring(v) for n, v in self.parts.items()
                    if n.endswith(('.xml', '.rels')) or n == '[Content_Types].xml'}
        self.document = self.xml['word/document.xml']
        self.body = self.document.find('w:body', NS)
        if self.document.tag != '{%s}document' % W or self.body is None:
            raise ValueError('missing Word document/body')

    def relationships(self, part):
        folder, name = posixpath.split(part)
        root = self.xml.get(posixpath.join(folder, '_rels', name + '.rels'))
        return [] if root is None else list(root)

    def target(self, part, rel):
        target = rel.get('Target', '')
        return posixpath.normpath(posixpath.join(posixpath.dirname(part), target)) if not target.startswith('/') else target[1:]

    def related(self, kind):
        return [(rel, self.target('word/document.xml', rel))
                for rel in self.relationships('word/document.xml')
                if rel.get('Type') == R + '/' + kind and rel.get('TargetMode') != 'External']


class Formatting:
    """Resolve defaults -> basedOn paragraph style -> paragraph -> character style -> run."""
    def __init__(self, package):
        root = package.xml.get('word/styles.xml', ET.Element('styles'))
        self.styles = {attr(s, 'styleId'): s for s in root.findall('w:style', NS)}
        self.default = next((attr(s, 'styleId') for s in self.styles.values()
                             if attr(s, 'type') == 'paragraph' and attr(s, 'default') == '1'), None)
        self.defaults = root.find('w:docDefaults', NS)

    def chain(self, style_id, seen=None):
        seen = set() if seen is None else seen
        if style_id not in self.styles:
            return []
        if style_id in seen:
            raise ValueError('cyclic style inheritance: ' + str(style_id))
        seen.add(style_id)
        style = self.styles[style_id]
        return self.chain(attr(style.find('w:basedOn', NS), 'val'), seen) + [style]

    def value(self, paragraph, run, prop, key):
        group = 'pPr' if prop == 'spacing' else 'rPr'
        containers = []
        if self.defaults is not None:
            containers.append(self.defaults.find('w:%sDefault/w:%s' % (group, group), NS))
        style_id = attr(paragraph.find('w:pPr/w:pStyle', NS), 'val') or self.default
        containers += [s.find('w:' + group, NS) for s in self.chain(style_id)]
        containers.append(paragraph.find('w:' + group, NS))
        if run is not None:
            containers += [s.find('w:rPr', NS) for s in self.chain(attr(run.find('w:rPr/w:rStyle', NS), 'val'))]
            containers.append(run.find('w:rPr', NS))
        value = None
        for container in containers:
            node = container.find('w:' + prop, NS) if container is not None else None
            found = attr(node, key)
            if found is not None:
                value = found
        return value


def verify(path):
    checks = []

    def check(name, ok, detail, nodes=(), warning=False):
        checks.append(dict(check=name, status=('PASS' if ok else 'WARN' if warning else 'FAIL'),
                           detail=detail, xml=[] if ok else [context(n) for n in nodes]))

    try:
        pkg = Package(path)
    except (OSError, BadZipFile, KeyError, ET.ParseError, ValueError) as exc:
        check('package_xml', False, str(exc))
        return checks
    check('package_xml', True, 'ZIP CRC, unique parts, XML syntax, document/body')
    types = pkg.xml.get('[Content_Types].xml')
    main_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
    ok = types is not None and any(n.tag == '{%s}Override' % CT and n.get('PartName') == '/word/document.xml'
                                  and n.get('ContentType') == main_type for n in types)
    check('content_types', ok, 'DOCX main-part content type', [types])
    root_rels = pkg.xml.get('_rels/.rels')
    ok = root_rels is not None and any(n.tag == '{%s}Relationship' % REL and n.get('Type') == R + '/officeDocument'
                                      and n.get('Target', '').lstrip('/') == 'word/document.xml' for n in root_rels)
    check('root_relationship', ok, 'officeDocument points to word/document.xml', [root_rels])
    sections = pkg.body.findall('.//w:sectPr', NS)
    check('section_present', bool(sections), '%d sections' % len(sections), [pkg.body])
    bad = [s for s in sections if len(s) == 0]
    check('section_nonempty', bool(sections) and not bad, '%d empty sections' % len(bad), bad or [None])
    paragraphs = pkg.body.findall('.//w:p', NS)
    bad = [p for p in paragraphs if p.find('w:pPr', NS) is None]
    check('paragraph_properties', bool(paragraphs) and not bad,
          '%d/%d body paragraphs lack pPr (including table cells)' % (len(bad), len(paragraphs)), bad or [pkg.body])
    fmt = Formatting(pkg)
    try:
        bad = [p for p in paragraphs if fmt.value(p, None, 'spacing', 'line') != '480'
               or fmt.value(p, None, 'spacing', 'lineRule') != 'auto']
        check('double_spacing', bool(paragraphs) and not bad, '%d paragraphs differ from 480/auto' % len(bad), bad or [pkg.body])
        runs = [(p, r) for p in paragraphs for r in p.findall('.//w:r', NS) if r.find('w:t', NS) is not None]
        bad_fonts = [r for p, r in runs if any(fmt.value(p, r, 'rFonts', k) != 'Times New Roman' for k in ('ascii', 'hAnsi'))]
        bad_sizes = [r for p, r in runs if fmt.value(p, r, 'sz', 'val') != '24']
        check('font_times_new_roman', bool(runs) and not bad_fonts, '%d/%d text runs differ (ascii + hAnsi)' % (len(bad_fonts), len(runs)), bad_fonts or [pkg.body])
        check('font_size_12pt', bool(runs) and not bad_sizes, '%d/%d text runs differ from sz=24' % (len(bad_sizes), len(runs)), bad_sizes or [pkg.body])
    except ValueError as exc:
        check('style_resolution', False, str(exc), [pkg.xml.get('word/styles.xml')])
    bad = [s for s in sections if attr(s.find('w:pgSz', NS), 'w') != '12240' or attr(s.find('w:pgSz', NS), 'h') != '15840']
    check('letter_page_size', bool(sections) and not bad, 'all sections 12240 x 15840 twips', bad or [None])
    bad = [s for s in sections if any(attr(s.find('w:pgMar', NS), k) != '1440' for k in ('top', 'right', 'bottom', 'left'))]
    check('one_inch_margins', bool(sections) and not bad, 'all sections: top/right/bottom/left=1440', bad or [None])
    headers = pkg.related('header')
    valid = [(r, p) for r, p in headers if p in pkg.xml and pkg.xml[p].tag == '{%s}hdr' % W]
    check('header_part', bool(valid) and len(valid) == len(headers), '%d linked header parts' % len(valid), [pkg.xml.get('word/_rels/document.xml.rels')], warning=not headers)
    references = [n.get('{%s}id' % R) for s in sections for n in s.findall('w:headerReference', NS)]
    used = [(r, p) for r, p in valid if r.get('Id') in references]
    check('header_used', bool(used), '%d section-linked headers' % len(used), sections, warning=not references)
    bad = []
    for _, part in used:
        header = pkg.xml[part]
        instructions = [n.get('{%s}instr' % W, '') for n in header.iter('{%s}fldSimple' % W)]
        instructions += [''.join(n.text or '' for n in header.iter('{%s}instrText' % W))]
        if not any(re.search(r'(^|\s)PAGE(\s|$)', text, re.I) for text in instructions):
            bad.append(header)
    check('header_page_field', bool(used) and not bad, 'PAGE field in each used header (PAGEREF does not count)', bad or sections)
    return checks


def print_checks(checks):
    print('| Check | Result | Detail |\n| --- | --- | --- |')
    for row in checks:
        print('| {check} | {status} | {detail} |'.format(**row))
    for row in checks:
        if row['status'] == 'FAIL':
            print('\nFAIL XML: ' + row['check'])
            for xml in row['xml']:
                print(xml)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('docx', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    checks = verify(args.docx)
    print_checks(checks)
    if args.json:
        args.json.write_text(json.dumps(checks, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return int(any(r['status'] == 'FAIL' for r in checks))


if __name__ == '__main__':
    sys.exit(main())

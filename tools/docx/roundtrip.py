#!/usr/bin/env python3
"""EXReader read/export/re-read probe, independently measured with ZIP/XML.

Manifest: {"documents": [{"id": "...", "path": "...", "sha256": "..."}]}.
Only hashes/counts are persisted; source text stays local. Exit 1 on ANY drift.
"""
import argparse
import ctypes as c
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from zipfile import BadZipFile
from verify_docx import Package, W, NS, attr, verify


def digest(data):
    return hashlib.sha256(data).hexdigest()


def metrics(path):
    pkg = Package(path)
    roots = [pkg.body]
    notes = []
    for kind, name in [('footnotes', 'footnote'), ('endnotes', 'endnote')]:
        for _, part in pkg.related(kind):
            root = pkg.xml[part]
            normal = [n for n in root.findall('w:' + name, NS) if attr(n, 'type') in (None, 'normal')]
            roots.extend(normal)
            if kind == 'footnotes':
                notes.extend(normal)
    text = ''.join(n.text or '' for root in roots for n in root.iter('{%s}t' % W))
    # Count image occurrences, not unused media files; hash every image payload too.
    images = [n for root in roots for n in root.iter() if n.tag in (
        '{http://schemas.openxmlformats.org/drawingml/2006/main}blip',
        '{urn:schemas-microsoft-com:vml}imagedata')]
    sections = pkg.body.findall('.//w:sectPr', NS)
    margins = [{k: attr(s.find('w:pgMar', NS), k) for k in ('top', 'right', 'bottom', 'left')}
               for s in sections]
    return dict(paragraphs=len(pkg.body.findall('.//w:p', NS)), characters=len(text),
                tables=len(pkg.body.findall('.//w:tbl', NS)), images=len(images), footnotes=len(notes),
                section_margins=margins, text_sha256=digest(text.encode()),
                image_sha256=sorted(digest(v) for n, v in pkg.parts.items() if n.startswith('word/media/')))


METRICS = ('paragraphs', 'characters', 'tables', 'images', 'footnotes', 'section_margins')


def differences(before, after):
    rows = []
    for name in METRICS:
        a, b = before[name], after[name]
        row = dict(metric=name, before=a, after=b, status='PASS' if a == b else 'FAIL')
        if a != b:
            if isinstance(a, int):
                row.update(delta=b-a, lost=max(0, a-b))
            else:
                row['lost_sections'] = max(0, len(a)-len(b))
                row['changed_sections'] = [i+1 for i in range(max(len(a), len(b)))
                                           if (a[i] if i < len(a) else None) != (b[i] if i < len(b) else None)]
        rows.append(row)
    return rows


class Error(c.Structure):
    _fields_ = [('code', c.c_int), ('message', c.c_char * 256)]


class Engine:
    def __init__(self, library):
        self.directory = os.add_dll_directory(str(library.parent)) if os.name == 'nt' else None
        self.dll = c.CDLL(str(library))
        ptr, size = c.c_void_p, c.c_size_t
        for name, result, args in [
            ('document_open', c.c_int, [c.c_char_p, c.POINTER(ptr), c.POINTER(Error)]),
            ('document_format', c.c_int, [ptr]),
            ('document_export', c.c_int, [ptr, c.c_int, c.POINTER(ptr), c.POINTER(size), c.POINTER(Error)]),
            ('document_text', ptr, [ptr, c.POINTER(size)]),
            ('document_free', None, [ptr]), ('free', None, [ptr])]:
            fn = getattr(self.dll, 'exr_' + name)
            fn.restype, fn.argtypes = result, args
            setattr(self, name, fn)

    def open(self, path):
        doc, err = c.c_void_p(), Error()
        status = self.document_open(str(path).encode('utf-8'), c.byref(doc), c.byref(err))
        if status:
            raise RuntimeError('EXReader open status=%d' % status)
        return doc

    def text_hash(self, doc):
        size = c.c_size_t()
        ptr = self.document_text(doc, c.byref(size))
        text = c.string_at(ptr, size.value)
        return dict(characters=len(text.decode('utf-8')), sha256=digest(text))

    def roundtrip(self, source, output):
        doc = self.open(source)
        data, size, err = c.c_void_p(), c.c_size_t(), Error()
        try:
            before = self.text_hash(doc)
            status = self.document_export(doc, self.document_format(doc), c.byref(data), c.byref(size), c.byref(err))
            if status:
                raise RuntimeError('EXReader export status=%d' % status)
            output.write_bytes(c.string_at(data, size.value))
        finally:
            if data.value:
                self.free(data)
            self.document_free(doc)
        copy = self.open(output)
        try:
            after = self.text_hash(copy)
        finally:
            self.document_free(copy)
        return dict(before=before, after=after, status='PASS' if before == after else 'FAIL')


def pdf_compare(source, output, folder, soffice, pdftotext):
    pages = []
    commands = []
    for label, path in [('original', source), ('export', output)]:
        dest = folder / label
        dest.mkdir(parents=True, exist_ok=True)
        profile = (dest / 'profile').resolve().as_uri()
        command = [soffice, '-env:UserInstallation=' + profile, '--headless', '--convert-to', 'pdf', '--outdir', str(dest), str(path)]
        pdf = dest / (path.stem + '.pdf')
        if pdf.exists():
            pdf.unlink()
        result = subprocess.run(command, capture_output=True, timeout=180)
        commands.append(dict(command=command, returncode=result.returncode))
        if result.returncode or not pdf.exists():
            raise RuntimeError('LibreOffice PDF conversion failed for ' + label)
        result = subprocess.run([pdftotext, '-enc', 'UTF-8', '-layout', str(pdf), '-'], capture_output=True, check=True, timeout=90)
        text = result.stdout.decode('utf-8')
        split = text.split('\f')
        if split[-1] == '':
            split.pop()
        pages.append(['\n'.join(line.rstrip() for line in page.splitlines()).strip() for page in split])
    a, b = pages
    changed = []
    for i in range(max(len(a), len(b))):
        old, new = a[i] if i < len(a) else '', b[i] if i < len(b) else ''
        if old != new:
            # Full text diff stays in ignored build output. Committed report has hashes/counts.
            (folder / ('page-%d.diff.txt' % (i+1))).write_text('\n'.join(difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile='original', tofile='export')), encoding='utf-8')
            changed.append(dict(page=i+1, before_sha256=digest(old.encode()), after_sha256=digest(new.encode())))
    return dict(status='PASS' if len(a) == len(b) and not changed else 'FAIL',
                original_pages=len(a), exported_pages=len(b), changed_pages=changed, commands=commands)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--library', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--soffice', default=shutil.which('soffice'))
    parser.add_argument('--pdftotext', default=shutil.which('pdftotext'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    engine = Engine(args.library.resolve(strict=True))
    report = dict(library_sha256=digest(args.library.read_bytes()), documents=[])
    failed = False
    for item in json.loads(args.manifest.read_text(encoding='utf-8-sig'))['documents']:
        record = dict(id=item['id'])
        try:
            source = Path(item['path'])
            if not source.is_absolute():
                source = (args.manifest.parent / source).resolve()
            record['source_sha256'] = digest(source.read_bytes())
            if record['source_sha256'] != item['sha256']:
                raise ValueError('source SHA256 mismatch')
            folder = args.output / item['id']
            folder.mkdir(exist_ok=True)
            output = folder / 'export.docx'
            record['before'] = metrics(source)
            record['sdk_reread'] = engine.roundtrip(source, output)
            record['after'] = metrics(output)
            record['metrics'] = differences(record['before'], record['after'])
            record['failed_metrics'] = sum(r['status'] == 'FAIL' for r in record['metrics'])
            record['content_hashes_equal'] = {k: record['before'][k] == record['after'][k] for k in ('text_sha256', 'image_sha256')}
            record['verification'] = verify(output)
            if args.soffice and args.pdftotext:
                record['pdf'] = pdf_compare(source, output, folder / 'pdf', args.soffice, args.pdftotext)
            else:
                record['pdf'] = dict(status='SKIP', reason='soffice or pdftotext unavailable')
            record['status'] = 'FAIL' if (record['failed_metrics'] or not all(record['content_hashes_equal'].values())
                or record['sdk_reread']['status'] == 'FAIL' or any(r['status'] == 'FAIL' for r in record['verification'])
                or record['pdf']['status'] == 'FAIL') else 'PASS'
        except (OSError, ValueError, RuntimeError, KeyError, BadZipFile, ET.ParseError, subprocess.SubprocessError) as exc:
            record.update(status='ERROR', error=str(exc))
        report['documents'].append(record)
        failed |= record['status'] != 'PASS'
        print(record['id'], record['status'], 'failed_metrics=', record.get('failed_metrics', 'unavailable'), flush=True)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return int(failed or not report['documents'])


if __name__ == '__main__':
    sys.exit(main())

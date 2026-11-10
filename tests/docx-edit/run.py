#!/usr/bin/env python3
"""Headless DOCX open/edit/save/reopen/undo regression, independently audited by #117."""
# SPDX-License-Identifier: MIT
import argparse
import ctypes as c
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from engine import Engine, ParaProps, RunProps, ok, text

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tests/fixtures/docx-edit'
LEFT, RIGHT = 'X5 split-left 中文|', 'X5 split-right β.'
INSERTS = ['X5 added 1 中文.', 'X5 added 2 beta.', 'X5 added 3 gamma.', LEFT + RIGHT,
           'X5 delete this paragraph.']
FONTS, SIZES = ['Calibri', 'Noto Serif', 'Arial'], [28, 32, 20]
PARAS = [dict(present=7, align=i + 1, left=720 + i * 240, right=i * 120,
              first=-240 if i == 1 else 360, before=60 + i * 60,
              after=120 + i * 60, line=360 + i * 120, rule=0) for i in range(3)]
GROUPS = {
    'content': ('paragraphs', 'characters', 'content_order'),
    'structure': ('tables', 'images', 'footnotes', 'section_margins', 'endnotes', 'sections',
                  'media_payloads', 'table_xml', 'drawing_xml', 'note_references',
                  'headers_and_page_fields', 'unmodified_opc_parts'),
    'properties': ('fonts', 'sizes', 'paragraph_properties')}
LABELS = dict(paragraphs='段落数', characters='字符数', tables='表格数', images='图片数',
              footnotes='脚注数', endnotes='尾注数', sections='节数', section_margins='各节页边距',
              fonts='字体', sizes='字号', paragraph_properties='段落属性（行距/缩进）',
              content_order='段落内容及标题样式', media_payloads='图片部件内容', table_xml='表格内容',
              drawing_xml='内嵌图片 XML', note_references='脚注/尾注引用',
              headers_and_page_fields='页眉及 PAGE 页码域', unmodified_opc_parts='未编辑的 OPC 部件')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def difference(label, expected, actual):
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(expected.keys() | actual.keys()):
            if key not in actual:
                return f'{label}.{key} 丢失'
            if key not in expected:
                return f'{label}.{key} 意外新增'
            if expected[key] != actual[key]:
                return difference(f'{label}.{key}', expected[key], actual[key])
    if isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
        if len(expected) != len(actual):
            return f'{label}元素数 {len(expected)}→{len(actual)}'
        for i, (old, new) in enumerate(zip(expected, actual)):
            if old != new:
                return difference(f'{label}[{i}]', old, new)
    return f'{label} {expected!s:.120}→{actual!s:.120}'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_validator(directory):
    for name in ('verify_docx.py', 'roundtrip.py'):
        require((directory / name).is_file(), f'#117 校验器缺失: {directory / name}; use --validator-dir')
    sys.path.insert(0, str(directory))
    return importlib.import_module('verify_docx'), importlib.import_module('roundtrip')


def signature(node):
    return (node.tag, sorted(node.attrib.items()), node.text or '', node.tail or '',
            [signature(child) for child in node])


def paragraph_text(node, v):
    return ''.join(n.text or '' for n in node.iter('{' + v.W + '}t'))


def measure(path, v, rt):
    pkg = v.Package(path)
    result = rt.metrics(path)  # The six original #117 measurements, unchanged.
    result['sections'] = len(pkg.body.findall('.//w:sectPr', v.NS))
    result['endnotes'] = sum(1 for _, part in pkg.related('endnotes')
        for note in pkg.xml[part].findall('w:endnote', v.NS)
        if v.attr(note, 'type') in (None, 'normal'))
    result['content_order'] = [(paragraph_text(p, v), v.attr(p.find('w:pPr/w:pStyle', v.NS), 'val'))
                               for p in pkg.body.findall('w:p', v.NS)]
    result['media_payloads'] = {n: digest(data) for n, data in pkg.parts.items() if n.startswith('word/media/')}
    result['table_xml'] = [signature(n) for n in pkg.body.findall('.//w:tbl', v.NS)]
    result['drawing_xml'] = [signature(n) for n in pkg.body.findall('.//w:drawing', v.NS)]
    result['note_references'] = {kind: [signature(n) for n in pkg.body.findall('.//w:' + kind, v.NS)]
                                for kind in ('footnoteReference', 'endnoteReference')}
    result['headers_and_page_fields'] = dict(
        parts={part: signature(pkg.xml[part]) for _, part in pkg.related('header')},
        references=[signature(n) for n in pkg.body.findall('.//w:headerReference', v.NS)])
    result['unmodified_opc_parts'] = {n: digest(data) for n, data in pkg.parts.items() if n != 'word/document.xml'}
    return pkg, result


def equivalent(original, restored, stage):
    require(original.parts.keys() == restored.parts.keys(), f'{stage}: OPC 部件清单改变')
    for name in original.parts:
        same = (signature(original.document) == signature(restored.document) if name == 'word/document.xml'
                else original.parts[name] == restored.parts[name])
        require(same, f'{stage}: {name} 与原夹具不等价')


def model_counts(api, doc, expected, stage):
    blocks, count = api.blocks(doc), c.c_size_t()
    api.sections(doc, c.byref(count))
    for name, value in dict(body_paragraphs=sum(b.kind == 0 for b in blocks),
                            tables=sum(b.kind == 1 for b in blocks), sections=count.value).items():
        require(value == expected[name], f'{stage}: 引擎 {LABELS.get(name, name)} {expected[name]}→{value}')


def properties(api, doc, pkg, originals, v):
    native = {text(p): p for p in api.paragraphs(doc)}
    xml = {paragraph_text(p, v): p for p in pkg.body.findall('w:p', v.NS)}
    actual, expected = ({name: {} for name in GROUPS['properties']} for _ in range(2))
    for i, original in enumerate(originals):
        key = original[0]
        require(key in native and key in xml, f'重开: 修改属性的原段落丢失: {key}')
        block, node = native[key], xml[key]
        require(block.count > 0, f'重开: 段落的文字 run 丢失: {key}')
        run = node.find('w:r', v.NS)
        require(run is not None, f'重开: 文字 run XML 丢失: {key}')
        font = run.find('w:rPr/w:rFonts', v.NS)
        actual['fonts'][key] = dict(native=block.runs[0].props.font.decode('utf-8'),
            xml=[v.attr(font, k) for k in ('ascii', 'hAnsi', 'eastAsia', 'cs')],
            present=block.runs[0].props.present & 3)
        expected['fonts'][key] = dict(native=FONTS[i], xml=[FONTS[i]] * 4, present=3)
        actual['sizes'][key] = dict(native=block.runs[0].props.size,
            xml=[v.attr(run.find('w:rPr/w:' + tag, v.NS), 'val') for tag in ('sz', 'szCs')])
        expected['sizes'][key] = dict(native=SIZES[i], xml=[str(SIZES[i])] * 2)
        pp, values = block.props, PARAS[i]
        spacing, indent = node.find('w:pPr/w:spacing', v.NS), node.find('w:pPr/w:ind', v.NS)
        actual['paragraph_properties'][key] = dict(native={k: getattr(pp, k) for k in values},
            spacing=[v.attr(spacing, k) for k in ('before', 'after', 'line', 'lineRule')],
            indent=[v.attr(indent, k) for k in ('left', 'right', 'firstLine', 'hanging')],
            align=v.attr(node.find('w:pPr/w:jc', v.NS), 'val'))
        expected['paragraph_properties'][key] = dict(native=values,
            spacing=[str(values[k]) for k in ('before', 'after', 'line')] + ['auto'],
            indent=[str(values['left']), str(values['right']),
                    str(values['first']) if values['first'] >= 0 else None,
                    str(-values['first']) if values['first'] < 0 else None],
            align=('center', 'right', 'both')[i])
    return actual, expected


def profile(path, fixture, v):
    """Keep #117's fixed formatting verdicts intact, including intended deviations."""
    rows = v.verify(path)
    expected = {name: 'PASS' for name in (
        'package_xml', 'content_types', 'root_relationship', 'section_present', 'section_nonempty',
        'paragraph_properties', 'double_spacing', 'font_times_new_roman', 'font_size_12pt',
        'letter_page_size', 'one_inch_margins', 'header_part', 'header_used', 'header_page_field')}
    for name in ('double_spacing', 'font_times_new_roman', 'font_size_12pt'):
        expected[name] = 'FAIL'  # The three original paragraphs were deliberately changed.
    if fixture == 'sections':
        expected['one_inch_margins'] = 'FAIL'  # This fixture deliberately has different margins.
    else:
        expected.update(header_part='WARN', header_used='WARN', header_page_field='FAIL')
    require({row['check']: row['status'] for row in rows} == expected,
            '#117 固定排版检查出现非预期变化: ' + json.dumps(rows, ensure_ascii=False))
    return rows


def remove_table(path, v):
    """Deliberate mutation of the actual engine output, used only by the negative control."""
    pkg = v.Package(path)
    table = pkg.body.find('w:tbl', v.NS)
    require(table is not None, '故意破坏测试: 找不到要删除的表格')
    pkg.body.remove(table)
    pkg.parts['word/document.xml'] = ET.tostring(pkg.document, encoding='utf-8')
    with ZipFile(path, 'w') as archive:
        for name, data in pkg.parts.items():
            archive.writestr(name, data)


def run(args):
    v, rt = load_validator(args.validator_dir)
    entry = next(row for row in json.loads((FIXTURES / 'manifest.json').read_text(encoding='utf-8'))['fixtures']
                 if row['id'] == args.fixture)
    source = FIXTURES / entry['path']
    original, before = measure(source, v, rt)
    initial_drift = [difference(LABELS[name], entry[name], before[name])
        for name in ('tables', 'images', 'footnotes', 'endnotes', 'sections', 'paragraphs') if before[name] != entry[name]]
    require(not initial_drift, '初始夹具结构: ' + '; '.join(initial_drift))
    require(source.stat().st_size == entry['bytes'] < 50_000, f'{source.name}: 夹具大小漂移或超过 50KB')
    require(digest(source.read_bytes()) == entry['sha256'], f'{source.name}: 夹具 SHA256 不匹配')
    require(len(original.related('header')) == entry['headers'], '初始页眉数与夹具清单不符')
    if args.fixture == 'table':
        rows = original.body.findall('w:tbl/w:tr', v.NS)
        require(len(rows) == 3 and all(len(row.findall('w:tc', v.NS)) == 3 for row in rows),
                '初始表格必须为 3×3')
    if args.fixture == 'heading':
        require(before['content_order'][0][1] == 'Heading1', '初始标题样式 Heading1 丢失')
    if args.fixture == 'sections':
        require(before['section_margins'][0] != before['section_margins'][1], '初始两节页边距必须不同')
    api = Engine(args.library.resolve(strict=True))
    doc = api.open(source)
    try:
        model_counts(api, doc, entry, '打开夹具')
        api.save(doc, args.output / 'opened.docx')
        opened, _ = measure(args.output / 'opened.docx', v, rt)
        equivalent(original, opened, '打开后无编辑保存')
        ids = [p.id for p in api.paragraphs(doc)]
        inserted, anchor = [], ids[0]
        for marker in INSERTS:
            anchor = api.insert(doc, anchor, marker)
            inserted.append(anchor)
        for i, block_id in enumerate(ids):
            pp = ParaProps(**PARAS[i])
            rp = RunProps(present=3, font=FONTS[i].encode('utf-8'), size=SIZES[i])
            ok(api.set_paragraph_props(doc, block_id, c.byref(pp)), f'修改原段落 {i + 1} 行距/缩进')
            ok(api.set_run_props(doc, block_id, 0, c.byref(rp)), f'修改原段落 {i + 1} 字体/字号')
        ok(api.split_paragraph(doc, inserted[3], 0, len(LEFT.encode('utf-8'))), '拆分含多字节文字的段落')
        ok(api.delete_block(doc, inserted[4]), '删除第 5 个插入段落')
        saved = args.output / 'edited.docx'
        api.save(doc, saved)
        if args.check_output:
            saved = args.check_output.resolve(strict=True)
        if args.damage_table:
            remove_table(saved, v)
        pkg, after = measure(saved, v, rt)
        copy = api.open(saved)  # Reopen the file written to disk through the engine API.
        try:
            api.save(copy, args.output / 'reopened.docx')
            equivalent(pkg, v.Package(args.output / 'reopened.docx'), '编辑产物重开后再次保存')
            expected = dict(before, paragraphs=before['paragraphs'] + 5,
                characters=before['characters'] + len(''.join(INSERTS[:4])),
                content_order=before['content_order'][:1] + [(s, None) for s in INSERTS[:3] + [LEFT, RIGHT]] +
                              before['content_order'][1:])
            expected['content_order'] = dict(xml=expected['content_order'],
                native=[p[0] for p in expected['content_order']])
            after['content_order'] = dict(xml=after['content_order'], native=[text(p) for p in api.paragraphs(copy)])
            props_actual, props_expected = properties(api, copy, pkg, before['content_order'], v)
            after.update(props_actual)
            expected.update(props_expected)
            rows = [dict(metric=name, label=LABELS[name], status='PASS' if after[name] == expected[name] else 'FAIL',
                         expected=expected[name], actual=after[name]) for name in GROUPS[args.case]]
            raw_profile = profile(saved, args.fixture, v)
            report = dict(fixture=args.fixture, case=args.case, source_sha256=entry['sha256'],
                library=str(args.library.resolve()), library_sha256=digest(args.library.read_bytes()),
                validator_sources={n: digest((args.validator_dir / n).read_bytes()) for n in ('verify_docx.py', 'roundtrip.py')},
                validated_output=str(saved.resolve()), output_sha256=digest(saved.read_bytes()),
                metrics=rows, validator_fixed_profile=raw_profile,
                edits=dict(insert=5, paragraph_properties=3, run_properties=3, split=1, delete=1))
            (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            failures = [difference(r['label'], r['expected'], r['actual']) for r in rows if r['status'] == 'FAIL']
            require(not failures, f'{args.fixture}/{args.case} 保存重开: ' + '; '.join(failures))
            model_counts(api, copy, dict(entry, body_paragraphs=entry['body_paragraphs'] + 5), '保存重开')
        finally:
            api.doc_free(copy)
        for i in range(13):  # 5 inserts + 3 paragraph props + 3 run props + split + delete.
            ok(api.undo(doc), f'撤销 {i + 1}/13')
        require(api.undo(doc) == 1, '撤销到初始后历史栈仍有记录（预期 EXR_ARGUMENT）')
        model_counts(api, doc, entry, '撤销到初始')
        restored = args.output / 'undo.docx'
        api.save(doc, restored)
        undone, _ = measure(restored, v, rt)
        equivalent(original, undone, '撤销到初始')
        check = api.open(restored)
        try:
            api.save(check, args.output / 'undo-reopened.docx')
            equivalent(original, v.Package(args.output / 'undo-reopened.docx'), '撤销保存后再重开')
        finally:
            api.doc_free(check)
        report.update(status='PASS', undo_commands=13, undo_equivalence='all OPC parts; main XML tree equal')
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'{args.fixture}/{args.case}: {len(rows)}/{len(rows)} metrics PASS; 13 undo commands; original package equivalent')
    finally:
        api.doc_free(doc)


def negative(args):
    command = [sys.executable, str(Path(__file__).resolve()), '--library', str(args.library),
        '--validator-dir', str(args.validator_dir), '--fixture', 'table', '--case', 'structure',
        '--output', str(args.output / 'broken'), '--damage-table']
    result = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=60)
    diagnostic = result.stdout + result.stderr
    (args.output / 'negative.txt').write_text(diagnostic, encoding='utf-8')
    require(result.returncode == 1 and '表格数 1→0' in diagnostic,
            f'故意删表未被正确拦截: exit={result.returncode}\n{diagnostic}')
    print('PASS: 删除编辑产物中的表格后，子用例 exit=1，诊断包含“表格数 1→0”。')
    (args.output / 'report.json').write_text(json.dumps(dict(status='PASS', child_exit=result.returncode,
        expected_diagnostic='表格数 1→0', diagnostic=diagnostic), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--validator-dir', type=Path, default=ROOT / 'tools/docx')
    parser.add_argument('--fixture', choices=('plain', 'heading', 'table', 'image', 'notes', 'sections'), default='table')
    parser.add_argument('--case', choices=tuple(GROUPS), default='structure')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--negative-table', action='store_true')
    controls = parser.add_mutually_exclusive_group()
    controls.add_argument('--damage-table', action='store_true', help='Deliberately corrupt engine output; must exit 1.')
    controls.add_argument('--check-output', type=Path, help='Validate an existing edited artifact against the same edit batch.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / 'report.json'
    report_path.write_text(json.dumps(dict(status='RUNNING', fixture=args.fixture, case=args.case)), encoding='utf-8')
    try:
        negative(args) if args.negative_table else run(args)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError, BadZipFile, ET.ParseError, subprocess.SubprocessError) as exc:
        report = json.loads(report_path.read_text(encoding='utf-8'))
        report.update(status='FAIL', error=str(exc))
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'FAIL {args.fixture}/{args.case}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

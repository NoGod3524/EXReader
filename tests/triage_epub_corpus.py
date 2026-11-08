#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Replay the 1,024 recorded mutations in both modes, retaining per-case verdicts.

Opt-in evidence run (not a ctest): python tests/triage_epub_corpus.py --help.
Only recipes, hashes and diagnostics are persisted; book bytes use temp files.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'compat'))
from malformed_corpus import BASELINE, BASELINE_SHA256, Corpus, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--font', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be positive')
    data = args.baseline.read_bytes()
    assert sha(data) == BASELINE_SHA256
    corpus = Corpus(data)
    original = [json.loads(s) for s in (ROOT / 'evidence/malformed-input-20261107/results.jsonl')
                .read_text(encoding='utf-8').splitlines()]
    engine, font = args.engine.resolve(), args.font.resolve()

    def probe(path, strict):
        command = [str(engine), str(path), str(font)] + (['--strict'] if strict else [])
        result = subprocess.run(command, capture_output=True, timeout=3)
        report = json.loads(result.stdout)
        return dict(exit_code=result.returncode, status=report['status'], stage=report['stage'],
                    complete=report['complete'], stderr=result.stderr.decode('utf-8').strip())

    with tempfile.TemporaryDirectory(prefix='exr-triage-control-') as temp:
        control = Path(temp) / 'control.epub'
        control.write_bytes(data)
        controls = {mode: probe(control, mode == 'strict') for mode in ('tolerant', 'strict')}
        assert all(r['exit_code'] == 0 and r['complete'] for r in controls.values()), controls

    def run(old):
        category, number = old['case'].rsplit('-', 1)
        body, recipe = corpus.generate(category, int(number))
        assert sha(body) == old['sha256'], old['case']
        with tempfile.TemporaryDirectory(prefix='exr-triage-') as temp:
            path = Path(temp) / 'input.epub'
            path.write_bytes(body)
            tolerant, strict = probe(path, False), probe(path, True)
        # Each recorded mutation is a structural violation in strict mode. The
        # original "passed" bucket means explicit rejection, not readable input.
        rejected = strict['exit_code'] == 1 and strict['status'] != 0 and all(
            word in strict['stderr'] for word in ('member', 'expected', 'found'))
        unchanged = (tolerant['exit_code'] == old['exit_code'] and
                     tolerant['status'] == old['engine_status'] and
                     tolerant['complete'] == old['complete'] and
                     bool(tolerant['stderr']) == old['has_error_text'])
        reasons = {
            'tail': f"删除尾部 {recipe.get('bytes')} 字节，ZIP 目录或成员不完整",
            'middle': f"偏移 {recipe.get('offset')} 删除 {recipe.get('bytes')} 字节，成员内容或目录偏移被破坏",
            'directory': f"目录字段 {recipe.get('field')} 改为 {recipe.get('value')}，与实际结构不符；严格模式拒绝",
            'container': '缺少 META-INF/container.xml，无法定位根包；移除成员：' + ', '.join(recipe.get('removed_members', [])),
            'mimetype': f"内容为 {recipe.get('replacement_ascii')}，应精确为 application/epub+zip；严格模式拒绝",
            'case': f"ZIP 中 OPF 改名为 {recipe.get('renamed_opf')}，container 所指精确路径不存在",
            'missing': f"spine 项 {recipe.get('idref')} 指向不存在的 {recipe.get('href')}，正文不完整",
            'duplicate': f"manifest 新 id={recipe.get('duplicate_id')} 重复 href={recipe.get('href')}，ZIP 重复 member={recipe.get('zip_name')}，资源身份有歧义",
        }
        if category == 'directory':
            offset, width = recipe['offset'], recipe['width']
            expected = int.from_bytes(data[offset:offset + width], 'little')
            reasons[category] = f"ZIP 字段 {recipe['field']}@{offset} 应为 {expected}，实际 {recipe['value']}"
            if old['bucket'] == 'investigate':
                reasons[category] += '；仅未读取的 mimetype 条目损坏，不存在本地头扫描恢复'
        return dict(case=old['case'], category=category, sha256=sha(body), recipe=recipe,
                    conclusion='应当报错（严格模式）',
                    reason=reasons[category],
                    original_bucket=old['bucket'], strict=strict, tolerant=tolerant,
                    strict_hit=rejected, tolerant_unchanged=unchanged)

    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for record in pool.map(run, original):
            records.append(record)
            if len(records) % 128 == 0:
                print(f'{len(records)}/1024', flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'cases.jsonl').write_text(''.join(
        json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
    summary = dict(total=len(records), workers=args.workers, timeout_seconds=3,
                   strict_expected=len(records),
                   strict_hits=sum(r['strict_hit'] for r in records),
                   pending_resolved=sum(r['strict_hit'] for r in records
                                        if r['original_bucket'] == 'investigate'),
                   tolerant_original_passes=sum(r['tolerant_unchanged'] for r in records
                                                if r['original_bucket'] == 'passed'),
                   tolerant_accepted=sum(r['tolerant']['exit_code'] == 0 for r in records),
                   tolerant_unchanged=sum(r['tolerant_unchanged'] for r in records),
                   categories={category: dict(total=sum(r['category'] == category for r in records),
                                              strict_hits=sum(r['strict_hit'] for r in records
                                                              if r['category'] == category),
                                              tolerant_rejected=sum(r['tolerant']['exit_code'] == 1
                                                                    for r in records if r['category'] == category))
                               for category in Counter(r['category'] for r in records)},
                   controls=controls, engine_sha256=sha(engine.read_bytes()),
                   runtime_libraries={p.name: sha(p.read_bytes()) for p in engine.parent.glob('*exreader*.dll')},
                   font_sha256=sha(font.read_bytes()), baseline_sha256=sha(data),
                   harness_sha256=sha(Path(__file__).read_bytes()),
                   failures=[r['case'] for r in records if not r['strict_hit'] or not r['tolerant_unchanged']])
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return int(bool(summary['failures']))


if __name__ == '__main__':
    sys.exit(main())

"""Exercise existing corpus drivers and merge gcov data without changing the SDK."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import ctypes as c
import gzip
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from analyze import ROOT, progress, write_json

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'tools/regress'))
import run_realbooks as regression


def write_gzip(path, value):
    with gzip.open(path, 'wt', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False)


def render_book(job):
    book, build, out, bridge, font, layout = job
    # Each worker writes its own profile files; ctest and other workers cannot race.
    os.environ['GCOV_PREFIX'] = str(out / 'local/runtime-coverage' / f'b{os.getpid()}')
    os.environ['GCOV_PREFIX_STRIP'] = str(len(build.parts))
    sys.path.insert(0, str(ROOT / 'docs/ui/acceptance'))
    from check_font_manager_host import render
    return render(book, str(build / 'libexreader.dll'), str(bridge), font, layout)


def books(args):
    manifest = regression.read_json(ROOT / 'tools/regress/corpus.json')
    layout = regression.read_json(ROOT / 'tools/regress/layout.json')
    started = time.monotonic()
    results = {}
    with ProcessPoolExecutor(max_workers=4) as pool:
        pending = [pool.submit(render_book, (book, args.build, args.output, args.bridge, args.font, layout))
                   for book in manifest['books']]
        for future in as_completed(pending):
            result = future.result()
            results[result['id']] = result
            write_gzip(args.output / 'realbooks.json.gz', list(results.values()))
            progress(args.output, f'Real book {len(results)}/19: {result["id"]}: '
                     f'{result["status"]}, {result["page_count"]} pages')
    results = [results[book['id']] for book in manifest['books']]
    result = dict(schema=1, pixel_contract='sha256/visible-row-major-RGBA8/white/v1',
                  layout=layout, font_sha256=regression.file_hash(args.font),
                  environment=dict(system=platform.system(), machine=platform.machine()),
                  dll_sha256=regression.file_hash(args.build / 'libexreader.dll'),
                  bridge_sha256=regression.file_hash(args.bridge),
                  source_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  books=results, content_fingerprint=regression.fingerprint(results),
                  elapsed_seconds=time.monotonic() - started)
    write_gzip(args.output / 'realbooks.json.gz', result)
    diff = regression.compare(regression.read_json(args.baseline), result)
    write_json(args.output / 'realbooks.diff.json', diff)
    progress(args.output, f'Real books complete: {len(results)} books, '
             f'{sum(b["page_count"] for b in results)} pages, '
             f'{diff["hash_changed_pages"]} changed hashes; needs_review={diff["needs_review"]}')
    assert len(results) == 19 and not diff['needs_review'], diff


def fixture_kind(path):
    if path.suffix.lower() in {'.epub', '.pdf', '.cbz', '.mobi', '.azw3', '.fb2', '.html', '.docx', '.rtf'}:
        return 'document'
    if path.suffix.lower() in {'.png', '.jpg', '.gif', '.bmp', '.webp', '.tif', '.avif'}:
        return 'image'
    if path.suffix.lower() in {'.ttf', '.otf', '.ttc'}:
        return 'font'
    return 'reference_or_test_data'


def fixtures(args):
    if (args.output / 'fixtures.jsonl').exists():
        raise FileExistsError('Use a fresh output directory to avoid mixing fixture runs')
    os.environ['GCOV_PREFIX'] = str(args.output / 'local/runtime-coverage/fixtures')
    os.environ['GCOV_PREFIX_STRIP'] = str(len(args.build.parts))
    sdk = regression.SDK(args.build / 'libexreader.dll')
    decode = sdk.dll.exr_image_decode
    decode.argtypes = [c.c_void_p, c.c_size_t, c.POINTER(regression.Bitmap), c.POINTER(regression.Error)]
    decode.restype = c.c_int
    records = []
    inventory = sorted(p for p in (ROOT / 'tests/fixtures').rglob('*') if p.is_file())
    for number, path in enumerate(inventory, 1):
        kind = fixture_kind(path)
        record = dict(file=path.relative_to(ROOT).as_posix(), kind=kind,
                      sha256=regression.file_hash(path), bytes=path.stat().st_size)
        if kind == 'document':
            command = [str(args.build / 'exreader-check-document.exe'), str(path), str(args.font)]
            try:
                result = subprocess.run(command, capture_output=True, timeout=60,
                                        encoding='utf-8', errors='replace')
                record.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
                try:
                    record['probe'] = json.loads(result.stdout)
                    record['outcome'] = 'complete' if record['probe']['complete'] else 'sdk_rejected'
                except (json.JSONDecodeError, KeyError):
                    record['outcome'] = 'process_failure'
            except subprocess.TimeoutExpired:
                record['outcome'] = 'timeout_60s'
        elif kind == 'image':
            data = path.read_bytes()
            bitmap, error = regression.Bitmap(), regression.Error()
            code = decode(data, len(data), c.byref(bitmap), c.byref(error))
            record.update(status=code, outcome='decoded' if code == 0 else 'sdk_rejected',
                          width=bitmap.width, height=bitmap.height)
            sdk.bitmap_free(c.byref(bitmap))
        elif kind == 'font':
            font, error = c.c_void_p(), regression.Error()
            code = sdk.font_open(str(path).encode('utf-8'), c.byref(font), c.byref(error))
            record.update(status=code, outcome='opened' if code == 0 else 'sdk_rejected')
            sdk.font_free(font)
        else:
            record['outcome'] = 'inventory_only_ctest_owns_protocol'
        assert regression.file_hash(path) == record['sha256'], path
        records.append(record)
        with (args.output / 'fixtures.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        if kind != 'reference_or_test_data':
            progress(args.output, f'Fixture {number}/{len(inventory)}: {record["file"]}: {record["outcome"]}')
    summary = dict(total_files=len(records), kinds=dict(Counter(r['kind'] for r in records)),
                   outcomes=dict(Counter(r['outcome'] for r in records)),
                   pages=sum(r.get('probe', {}).get('pages', 0) for r in records),
                   document_page_limit=None, document_timeout_seconds=60,
                   reference_files_are_not_claimed_as_individually_executed=True)
    write_json(args.output / 'fixtures-summary.json', summary)
    progress(args.output, f'Fixtures complete: {json.dumps(summary)}')
    assert not any(r['outcome'] in ('timeout_60s', 'process_failure') for r in records)


def coverage(args):
    files = {}
    invocations = []
    notes = sorted(args.build.rglob('*.gcno'))
    # Attach original notes to isolated process counters, then union reachability.
    for group in sorted((args.output / 'local/runtime-coverage').iterdir()):
        for counter in sorted(group.rglob('*.gcda')):
            note = counter.with_suffix('.gcno')
            original = (args.build / counter.relative_to(group)).with_suffix('.gcno')
            assert original.is_file(), (counter, original)
            shutil.copyfile(original, note)
            notes.append(note)
    with gzip.open(args.output / 'gcov-raw.jsonl.gz', 'wt', encoding='utf-8') as raw:
        for number, note in enumerate(notes, 1):
            command = ['gcov', '--json-format', '--stdout', str(note)]
            result = subprocess.run(command, cwd=args.build, capture_output=True,
                                    encoding='utf-8', errors='replace')
            invocations.append(dict(command=command, exit_code=result.returncode, stderr=result.stderr))
            if result.returncode:
                raise RuntimeError(result.stderr)
            data = json.loads(result.stdout)
            raw.write(json.dumps(dict(note=str(note), data=data)) + '\n')
            for source in data['files']:
                path = Path(source['file']).resolve()
                if not path.is_relative_to(ROOT / 'src') or path.suffix != '.c':
                    continue
                name = path.relative_to(ROOT).as_posix()
                merged = files.setdefault(name, dict(lines={}, functions={}))
                for line in source['lines']:
                    key = line['line_number']
                    merged['lines'][key] = max(merged['lines'].get(key, 0), line['count'])
                for function in source['functions']:
                    key = (function['name'], function['start_line'])
                    merged['functions'][key] = max(merged['functions'].get(key, 0), function['execution_count'])
            if number % 100 == 0:
                progress(args.output, f'gcov: {number}/{len(notes)} objects read')
    records = []
    for name, data in sorted(files.items()):
        total = len(data['lines'])
        hit = sum(count > 0 for count in data['lines'].values())
        functions = [dict(name=key[0], line=key[1], executed=count > 0, max_instance_calls=count)
                     for key, count in sorted(data['functions'].items())]
        records.append(dict(file=name, lines=total, covered_lines=hit,
                            line_percent=round(100 * hit / total, 2) if total else None,
                            functions=len(functions), covered_functions=sum(f['executed'] for f in functions),
                            covered_line_numbers=sorted(n for n, count in data['lines'].items() if count > 0),
                            uncovered_line_numbers=sorted(n for n, count in data['lines'].items() if count == 0),
                            function_details=functions))
    line_total = sum(r['lines'] for r in records)
    line_hits = sum(r['covered_lines'] for r in records)
    summary = dict(scope='src/*.c; union of executed lines/functions across all object instances',
                   compiler_optimization='-O1', sanitizer=False, object_files=len(notes),
                   source_files=len(records), executed_source_files=sum(r['covered_lines'] > 0 for r in records),
                   lines=line_total, covered_lines=line_hits, line_percent=round(100 * line_hits / line_total, 2),
                   functions=sum(r['functions'] for r in records),
                   covered_functions=sum(r['covered_functions'] for r in records), files=records)
    write_json(args.output / 'coverage.json', summary)
    write_json(args.output / 'gcov-commands.json', invocations)
    expected = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'src').glob('*.c')}
    assert set(files) == expected, sorted(expected - files.keys())
    progress(args.output, f'Coverage complete: {line_hits}/{line_total} lines ({summary["line_percent"]}%), '
             f'{summary["covered_functions"]}/{summary["functions"]} functions, {len(records)} source files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['books', 'fixtures', 'coverage'])
    parser.add_argument('--build', type=lambda s: Path(s).resolve(), required=True)
    parser.add_argument('--output', type=lambda s: Path(s).resolve(), required=True)
    parser.add_argument('--font', type=lambda s: Path(s).resolve())
    parser.add_argument('--bridge', type=lambda s: Path(s).resolve())
    parser.add_argument('--baseline', type=lambda s: Path(s).resolve())
    args = parser.parse_args()
    globals()[args.action](args)

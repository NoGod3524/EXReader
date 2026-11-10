"""Isolated every-page book rendering and deterministic fixture mutations."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from runtime_routes import ROOT, OUT, LOCAL, msvc_env, progress
sys.path.insert(0, str(ROOT / 'tools/regress'))
import run_realbooks as regression


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def environment(mode):
    env = msvc_env() if mode != 'coverage' else os.environ.copy()
    env['ASAN_OPTIONS'] = 'alloc_dealloc_mismatch=1:halt_on_error=1'
    build = LOCAL / {'asan':'a', 'coverage':'g', 'control':'m'}[mode]
    if mode == 'asan':
        runtime = Path(shutil.which('cl', path=env['PATH'])).parent / 'clang_rt.asan_dynamic-x86_64.dll'
        if not (build / runtime.name).exists():
            shutil.copy2(runtime, build / runtime.name)
    elif mode == 'coverage':
        counters = OUT / 'local/runtime-coverage/w'
        counters.mkdir(parents=True, exist_ok=True)
        env['GCOV_PREFIX'] = str(counters)
        env['GCOV_PREFIX_STRIP'] = str(len(build.parts))
    return build, env


def book_worker(args):
    sys.path.insert(0, str(ROOT / 'docs/ui/acceptance'))
    from check_font_manager_host import render
    manifest = regression.read_json(ROOT / 'tools/regress/corpus.json')
    build = LOCAL / {'asan':'a', 'coverage':'g', 'control':'m'}[args.mode]
    if args.mode == 'coverage':
        os.environ['GCOV_PREFIX'] = str(OUT / f'local/runtime-coverage/b{args.worker_book}')
    book = manifest['books'][args.worker_book]
    assert regression.file_hash(book['path']) == book['sha256']
    result = render(book, str(build / ('libexreader.dll' if args.mode == 'coverage' else 'exreader.dll')),
                    str(build / 'quality-font-bridge.dll'), LOCAL / 'fonts/Reader.otf',
                    regression.read_json(ROOT / 'tools/regress/layout.json'))
    print(json.dumps(result, ensure_ascii=False))


def books(args):
    build, env = environment(args.mode)
    font = LOCAL / 'fonts/Reader.otf'
    font.parent.mkdir(parents=True, exist_ok=True)
    if not font.exists():
        shutil.copy2(ROOT.parent / 'EXReader-Windows-delivery-20261104/payload/Reader.otf', font)
    manifest = regression.read_json(ROOT / 'tools/regress/corpus.json')
    layout = regression.read_json(ROOT / 'tools/regress/layout.json')
    started = time.monotonic()
    records = {}
    def one(index):
        command = [sys.executable, '-X', 'utf8', __file__, args.mode, 'books', '--worker-book', str(index)]
        result = subprocess.run(command, env=env, capture_output=True, encoding='utf-8', errors='replace')
        (OUT / f'{args.mode}-book-{index:02}-stderr.txt').write_text(result.stderr, encoding='utf-8')
        if result.returncode:
            return dict(id=manifest['books'][index]['id'], status='process_failure', exit_code=result.returncode,
                        stdout=result.stdout, page_count=0)
        return json.loads(result.stdout)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(one, i): i for i in range(len(manifest['books']))}
        for future in as_completed(jobs):
            value = future.result()
            records[jobs[future]] = value
            progress(f'{args.mode} book {len(records)}/19: {value["id"]}: {value["status"]}, {value["page_count"]} pages')
    result = dict(schema=1, pixel_contract='sha256/visible-row-major-RGBA8/white/v1', layout=layout,
                  dll_sha256=regression.file_hash(build / ('libexreader.dll' if args.mode == 'coverage' else 'exreader.dll')),
                  bridge_sha256=regression.file_hash(build / 'quality-font-bridge.dll'),
                  source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                  font_sha256=regression.file_hash(font), environment=dict(system='Windows', machine='AMD64'),
                  books=[records[i] for i in sorted(records)], elapsed_seconds=time.monotonic()-started)
    result['content_fingerprint'] = regression.fingerprint(result['books'])
    with gzip.open(OUT / f'{args.mode}-realbooks.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False)
    baseline = regression.read_json(ROOT / 'docs/ui/evidence/annotations/books-after.json')
    diff = regression.compare(baseline, result)
    write(OUT / f'{args.mode}-realbooks.diff.json', diff)
    progress(f'{args.mode} books complete: {sum(b["page_count"] for b in result["books"])} pages; hash changes={diff["hash_changed_pages"]}')
    assert len(records) == 19 and all(b['status'] == 'ok' for b in records.values())


def kind(path):
    suffix = path.suffix.lower()
    if path.name in ('font-cff-regression.bin', 'font-image-regression.bin'): return 'font'
    if path.name in ('sample.txt', 'utf16.txt', 'fuzz-cbz-truncated.bin'): return 'document'
    if suffix in ('.epub', '.pdf', '.cbz', '.mobi', '.azw3', '.fb2', '.html', '.docx', '.rtf'): return 'document'
    if suffix in ('.png', '.jpg', '.gif', '.bmp', '.webp', '.tif', '.avif'): return 'image'
    if suffix in ('.ttf', '.otf', '.ttc'): return 'font'
    return {'.7z':'sevenz', '.sqlite':'library', '.conf':'configuration', '.wav':'audio',
            '.m4b':'audio_metadata'}.get(suffix, 'reference_or_test_data')


def fixtures(args):
    build, env = environment(args.mode)
    inventory = []
    jobs = []
    for index, path in enumerate(sorted(p for p in (ROOT / 'tests/fixtures').rglob('*') if p.is_file())):
        row = dict(file=path.relative_to(ROOT).as_posix(), sha256=regression.file_hash(path),
                   bytes=path.stat().st_size, kind=kind(path))
        inventory.append(row)
        if row['kind'] == 'reference_or_test_data': continue
        data = path.read_bytes()
        variants = [('original', data)]
        if not args.original_only:
            variants += [('empty', b''), ('half', data[:len(data)//2]),
                         ('header-xor', bytes(b ^ 0xff for b in data[:16])+data[16:])]
        for mutation, payload in variants:
            directory = LOCAL / f'{args.mode}-inputs' / str(index) / mutation
            directory.mkdir(parents=True, exist_ok=True)
            if row['kind'] == 'configuration':
                shutil.copytree(path.parent, directory, dirs_exist_ok=True)
            target = directory / (path.name if path.name != 'fuzz-cbz-truncated.bin' else 'fuzz-cbz-truncated.cbz')
            target.write_bytes(payload)
            if mutation == 'original' and row['kind'] not in ('configuration', 'library') and path.name != 'fuzz-cbz-truncated.bin':
                target = path
            jobs.append((row, mutation, target))
    write(OUT / f'{args.mode}-fixtures-inventory.json', inventory)
    def one(job):
        row, mutation, path = job
        command = ([str(build / 'exreader-check-document.exe'), str(path), str(ROOT / 'tests/fixtures/fonts/primary.ttf')]
                   if row['kind'] == 'document' else [str(build / 'typed-probe.exe'), row['kind'], str(path)])
        record = dict(file=row['file'], kind=row['kind'], mutation=mutation, sha256=regression.file_hash(path), command=command)
        job_env = env.copy()
        if args.mode == 'coverage':
            job_env['GCOV_PREFIX'] = str(OUT / f'local/runtime-coverage/f{threading.get_ident()}')
        try:
            result = subprocess.run(command, env=job_env, capture_output=True, timeout=120, encoding='utf-8', errors='replace')
            record.update(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
            try:
                probe = json.loads(result.stdout)
                record['probe'] = probe
                record['outcome'] = ('complete' if probe.get('complete', probe.get('status') == 0) else 'sdk_rejected')
                if result.returncode not in (0, 1): record['outcome'] = 'process_failure'
            except json.JSONDecodeError:
                record['outcome'] = 'process_failure'
        except subprocess.TimeoutExpired as error:
            record.update(outcome='timeout', stderr=(error.stderr or b'').decode('utf-8', errors='replace'))
        return record
    outcomes, original, mutation_counts = Counter(), Counter(), Counter()
    pages = 0
    with (OUT / f'{args.mode}-fixtures.jsonl').open('w', encoding='utf-8') as stream, ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(one, job) for job in jobs]
        for number, future in enumerate(as_completed(pending), 1):
            record = future.result()
            stream.write(json.dumps(record, ensure_ascii=False)+'\n'); stream.flush()
            outcomes[record['outcome']] += 1
            mutation_counts[record['mutation']] += 1
            if record['mutation'] == 'original': original[record['outcome']] += 1
            pages += record.get('probe', {}).get('pages', 0)
            if number % 200 == 0: progress(f'{args.mode} fixtures: {number}/{len(jobs)} inputs; {dict(outcomes)}')
    for row in inventory:
        assert regression.file_hash(ROOT / row['file']) == row['sha256'], row['file']
    summary = dict(inventory=len(inventory), executed_inputs=sum(r['kind']!='reference_or_test_data' for r in inventory),
                   invocations=len(jobs), kinds=dict(Counter(r['kind'] for r in inventory)),
                   outcomes=dict(outcomes), originals=dict(original), variants=dict(mutation_counts), pages=pages)
    write(OUT / f'{args.mode}-fixtures-summary.json', summary)
    progress(f'{args.mode} fixtures complete: {summary}')
    # Every abnormal process is retained for diagnosis; never treat an SDK rejection as an ASan pass.
    return not outcomes['process_failure'] and not outcomes['timeout']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['asan', 'coverage', 'control'])
    parser.add_argument('action', choices=['books', 'fixtures'])
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--worker-book', type=int)
    parser.add_argument('--original-only', action='store_true')
    arguments = parser.parse_args()
    if arguments.worker_book is not None: book_worker(arguments)
    elif arguments.action == 'books': books(arguments)
    else: raise SystemExit(0 if fixtures(arguments) else 1)

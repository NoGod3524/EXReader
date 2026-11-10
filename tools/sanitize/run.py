"""Run books, regenerated malformed EPUBs and existing regression seeds.

All input bytes, profiles and unfiltered process output remain outside the repo.
Only numeric JSON, input hashes and sanitizer reports are saved as evidence.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def diagnostics(stderr):
    """Keep sanitizer diagnostics and their last numeric context, discard book errors."""
    context, blocks, current = '', [], None
    for line in stderr.splitlines():
        if line.startswith(('AUDIT_CONTEXT ', 'AUDIT_RENDERED ')):
            if line.startswith('AUDIT_CONTEXT '):
                context = line
            current = None
        elif 'runtime error:' in line or re.search(r'ERROR: (AddressSanitizer|LeakSanitizer)', line):
            current = {'context': context, 'lines': [line]}
            blocks.append(current)
        elif current is not None:
            # Sanitizer-only continuation: callers pass no engine text into stacks.
            if re.match(r'\s*#\d+\s', line) or line.startswith(('SUMMARY:', '==', 'READ ', 'WRITE ', '    ', '0x', 'Shadow ', '=>', '  ')):
                current['lines'].append(line)
    return blocks


def execute(command, unit, args, group, timeout=1800):
    env = {k.upper(): v for k, v in os.environ.items()}
    rt = next((args.llvm / 'lib/clang').glob('*/lib/windows'))
    env['PATH'] = str(rt) + os.pathsep + str(args.llvm/'bin') + os.pathsep + env['PATH']
    env['ASAN_SYMBOLIZER_PATH'] = str(args.llvm/'bin/llvm-symbolizer.exe')
    env['ASAN_OPTIONS'] = 'symbolize=1:halt_on_error=1:alloc_dealloc_mismatch=1'
    env['UBSAN_OPTIONS'] = 'print_stacktrace=1:report_error_type=1'
    profiles = args.work / 'profiles' / group
    profiles.mkdir(parents=True, exist_ok=True)
    env['LLVM_PROFILE_FILE'] = str(profiles / (unit+'-%p.profraw'))
    started = time.perf_counter()
    timed_out = False
    try:
        result = subprocess.run([str(x) for x in command], env=env, capture_output=True,
                                timeout=timeout, creationflags=0x08000000 if os.name=='nt' else 0)
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = None, error.stdout or b'', error.stderr or b''
        timed_out = True
    (args.work/'raw').mkdir(exist_ok=True)
    (args.work/'raw'/(group+'-'+unit+'.stdout')).write_bytes(stdout)
    (args.work/'raw'/(group+'-'+unit+'.stderr')).write_bytes(stderr)
    metrics = None
    for line in stdout.decode('utf-8', errors='replace').splitlines():
        try:
            candidate = json.loads(line)
            if isinstance(candidate, dict):
                metrics = candidate
        except ValueError:
            pass
    reports = diagnostics(stderr.decode('utf-8', errors='replace'))
    replay = re.search(r'^replay: format=(\S+) bytes=(\d+) status=(\d+)$',
                       stdout.decode('utf-8', errors='replace'), re.M)
    contexts = re.findall(r'^AUDIT_CONTEXT .+$', stderr.decode('utf-8', errors='replace'), re.M)
    return dict(id=unit, group=group, exit_code=code, timed_out=timed_out,
                seconds=round(time.perf_counter()-started, 3), metrics=metrics,
                replay=dict(format=replay[1], bytes=int(replay[2]), status=int(replay[3])) if replay else None,
                diagnostics=reports, last_context=contexts[-1] if contexts else '',
                writing_mode_pages=dict(Counter(re.findall(r'^AUDIT_RENDERED mode=(\d+)$', stderr.decode('utf-8', errors='replace'), re.M))),
                stderr_sha256=hashlib.sha256(stderr).hexdigest())


def main(args):
    args.work.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    driver = args.build / 'exreader-sanitize.exe'
    if args.group=='controls':
        records = [execute([args.build/'sanitize-control.exe', kind], kind, args, 'controls', 60)
                   for kind in ('asan', 'ubsan')]
        assert any('AddressSanitizer' in str(r['diagnostics']) for r in records)
        assert any('runtime error:' in str(r['diagnostics']) for r in records)
    else:
        jobs = []
        with tempfile.TemporaryDirectory(prefix='exr-sanitize-', dir=args.work) as directory:
            if args.group=='books':
                books = json.loads((ROOT/'tools/regress/corpus.json').read_text())['books']
                for book in books:
                    path = Path(book['path'])
                    assert sha(path)==book['sha256'], book['id']
                    jobs.append((book['id'], path, {'sha256': book['sha256'], 'language':book['language']}))
            elif args.group=='malformed':
                spec = importlib.util.spec_from_file_location('malformed', ROOT/'tools/compat/malformed_corpus.py')
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                assert sha(module.BASELINE)==module.BASELINE_SHA256
                corpus = module.Corpus(module.BASELINE.read_bytes())
                # 25 cases/category, evenly covering the original 1..128 range.
                for category in module.CATEGORIES:
                    for n in range(25):
                        index = 1+n*127//24
                        body, recipe = corpus.generate(category, index)
                        unit = f'{category}-{index:03d}'
                        path = Path(directory)/(unit+'.epub')
                        path.write_bytes(body)
                        jobs.append((unit, path, dict(category=category, recipe=recipe, sha256=sha(path))))
                assert len({j[2]['sha256'] for j in jobs})==200
            elif args.group=='seeds':
                spec = importlib.util.spec_from_file_location('campaign', ROOT/'tools/run_reliability_campaign.py')
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for pipeline, names in module.CORPUS.items():
                    for name in names:
                        path = ROOT/'tests/fixtures'/name
                        jobs.append((pipeline+'-'+name.replace('/','-'), path,
                                     dict(sha256=sha(path), pipeline=pipeline, seed=name)))
                path = ROOT/'tests/fixtures/fuzz-cbz-truncated.bin'
                jobs.append(('fuzz-cbz-truncated', path, dict(sha256=sha(path), pipeline='parser', format='cbz')))

            if args.case:
                jobs = [j for j in jobs if j[0]==args.case]
                if not jobs:
                    raise ValueError('Unknown input id: '+args.case)

            def run(job):
                unit, path, metadata = job
                if args.group=='seeds':
                    pipeline = metadata['pipeline']
                    target = 'exreader-fuzz'+('' if pipeline=='parser' else '-'+pipeline)+'.exe'
                    command = [args.build/'engine'/target, '--replay', path]
                    if pipeline in ('layout','render'):
                        command += ['--font', args.font]
                    if 'format' in metadata:
                        command += ['--format', metadata['format']]
                else:
                    command = [driver, path, args.font]
                record = execute(command, unit, args, args.group)
                record.update(metadata)
                return record

            records = []
            # Incremental evidence makes an interrupted run measurable.
            with (args.output/(args.group+'.jsonl')).open('w', encoding='utf-8') as stream:
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    for future in as_completed([pool.submit(run, j) for j in jobs]):
                        record = future.result()
                        records.append(record)
                        stream.write(json.dumps(record, ensure_ascii=False)+'\n')
                        stream.flush()
                        print(json.dumps({k:record[k] for k in ('id','exit_code','seconds')}), flush=True)
            # Ensure the read-only book campaign did not alter input bytes.
            if args.group=='books':
                for _, path, metadata in jobs:
                    assert sha(path)==metadata['sha256']
    records.sort(key=lambda r:r['id'])
    (args.output/(args.group+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    summary = dict(group=args.group, timestamp_utc=datetime.now(timezone.utc).isoformat(),
                   units=len(records), pages=sum((r['metrics'] or {}).get('pages',0) for r in records),
                   completed=sum(bool((r['metrics'] or {}).get('complete')) for r in records),
                   replays_completed=sum(bool(r['replay']) and r['exit_code']==0 for r in records),
                   timed_out=sum(r['timed_out'] for r in records),
                   asan=sum('AddressSanitizer' in d['lines'][0] for r in records for d in r['diagnostics']),
                   ubsan=sum('runtime error:' in d['lines'][0] for r in records for d in r['diagnostics']),
                   engine_sha256=sha(driver), font_sha256=sha(args.font), workers=args.workers)
    (args.output/(args.group+'-summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group', choices=['controls','books','malformed','seeds'])
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'evidence/sanitize-20261107')
    parser.add_argument('--llvm', type=Path, default=Path(r'C:\Users\Oscar\Documents\Codex\sanitize-toolchain-20261107\llvm'))
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/msyh.ttc'))
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--case', help='Replay a single book id, variant id or seed id')
    main(parser.parse_args())

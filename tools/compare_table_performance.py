#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Alternate frozen baseline/candidate processes on the same 1 MiB auto table."""
import argparse
import json
from pathlib import Path
import statistics
import shutil
import subprocess
import zipfile

from check_corpus import digest
from run_benchmarks import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('font', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--rounds', type=int, default=5)
    args = parser.parse_args()
    if args.rounds < 5:
        parser.error('At least five alternating rounds are required')
    output = args.output.absolute()
    if output.exists():
        parser.error('Choose a new output directory')
    binaries = {'baseline': args.baseline.absolute(), 'candidate': args.candidate.absolute()}
    font = args.font.absolute()
    identities = {str(p): digest(p) for binary in binaries.values()
                  for p in [binary, *binary.parent.glob('*.dll'), *binary.parent.glob('libexreader*.so*'),
                            *binary.parent.glob('libexreader*.dylib')]}
    identities[str(font)] = digest(font)
    output.mkdir(parents=True)
    # Keep executable evidence runnable after the original build directories change.
    for name, binary in list(binaries.items()):
        runtime = output/'runtime'/name
        runtime.mkdir(parents=True)
        for source in (Path(p) for p in identities if Path(p).parent == binary.parent):
            shutil.copyfile(source, runtime/source.name)
        binaries[name] = runtime/binary.name
    shutil.copyfile(font, output/font.name)
    font = output/font.name
    frozen = {str(p): digest(p) for p in (output/'runtime').rglob('*') if p.is_file()}
    frozen[str(font)] = digest(font)
    fixture = Path(__file__).absolute().parents[1]/'tests/fixtures/table-fragments-large-fixed.epub'
    with zipfile.ZipFile(fixture) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files['chapter.xhtml'] = files['chapter.xhtml'].replace(b';table-layout:fixed', b'')
    book = output/'auto-table-1MiB.epub'
    with zipfile.ZipFile(book, 'w') as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name == 'mimetype' else zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    rows, samples = [], {'baseline': [], 'candidate': []}
    for round_index in range(args.rounds):
        order = ['baseline', 'candidate'] if round_index % 2 == 0 else ['candidate', 'baseline']
        for name in order:
            stdout = output/f'{round_index+1}-{name}.json'
            stderr = output/f'{round_index+1}-{name}.stderr.log'
            command = [str(binaries[name]), str(book), str(font), '--paging', '--max-pages', '1']
            row = {'round': round_index+1, 'variant': name, 'command': command,
                   'stdout': str(stdout), 'stderr': str(stderr), 'passed': False}
            try:
                with stdout.open('wb') as out, stderr.open('wb') as log:
                    process = subprocess.run(command, stdout=out, stderr=log, timeout=180)
                row['exit_code'] = process.returncode
                if process.returncode == 0:
                    record = json.loads(stdout.read_text(encoding='utf-8'))
                    validate(record)
                    assert record['layout_mode'] == 'paged' and record['mode'] == 'indexed_epub'
                    assert record['sample_count'] == 1 and not record['single_page_repaint']
                    samples[name].append(record)
                    row['passed'] = True
            except (subprocess.TimeoutExpired, OSError, ValueError, AssertionError, KeyError, TypeError):
                row['incomplete'] = True
            row['stdout_sha256'] = digest(stdout)
            row['stderr_sha256'] = digest(stderr)
            rows.append(row)
    unchanged = all(Path(p).is_file() and digest(Path(p)) == sha for p, sha in {**identities, **frozen}.items())
    complete = all(row['passed'] for row in rows) and unchanged
    medians = {name: {key: statistics.median(r[key] for r in records)
                     for key in ('first_visible_total_ms', 'first_layout_ms', 'peak_rss_bytes')}
               for name, records in samples.items() if records}
    complete = complete and medians.get('baseline', {}).get('first_visible_total_ms', 0) > 0
    ratio = medians['candidate']['first_visible_total_ms']/medians['baseline']['first_visible_total_ms'] if complete else None
    report = {'schema': 1, 'scope': '1 MiB auto table, first visible page and one continuation; fresh process per sample',
              'disk_cache': 'uncontrolled', 'rounds': args.rounds, 'identities': identities,
              'frozen_runtime': frozen,
              'identities_unchanged': unchanged, 'input_sha256': digest(book),
              'median': medians, 'first_visible_ratio': ratio,
              'passed': complete and ratio <= .5, 'samples': rows}
    (output/'comparison.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'complete': complete, 'first_visible_ratio': ratio, 'target_passed': report['passed']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

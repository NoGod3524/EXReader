#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Synthetic accounting checks, never acceptance campaign evidence."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).absolute().parents[1]/'tools'))
from run_reliability_campaign import (CORPUS, SCHEMA, SANITIZER_ENV, binary_name, digest, run,
                                      summarize, write_json)

SOURCE = 'a'*40
HASH = 'b'*64


def main():
    checks = 0
    files = {binary_name(t).removesuffix('.exe'): HASH for t in CORPUS}
    files.update({'CMakeCache.txt': HASH, 'libexreader.so.1': HASH})
    manifest = dict(schema=SCHEMA, source_sha=SOURCE, working_tree_clean=True,
                    sanitizers_requested=True, files=files,
                    sanitizer_symbols={k: dict(asan=True, ubsan=True) for k in files if k != 'CMakeCache.txt'})
    with tempfile.TemporaryDirectory(prefix='exreader-accounting-') as temporary:
        root = Path(temporary)
        proof = root/'build-manifest.json'
        write_json(proof, manifest)
        rows = []
        logs = {}
        for target in CORPUS:
            label = 'reached a parsed document' if target == 'parser' else 'completed the selected pipeline'
            logs[target] = ('fuzz: 100 iterations over %d seeds, 1 %s, no crash\n'
                            'process_cpu_seconds=3600.000000000 requested_cpu_seconds=3600\n'
                            % (len(CORPUS[target]), label)).encode()
            row = dict(schema=SCHEMA, target=target, source_sha=SOURCE, seed=1, effective_seed=1,
                       working_tree_clean=True, source_unchanged=True, sanitizers_requested=True,
                       sanitizer_environment=SANITIZER_ENV,
                       inputs_unchanged=True, passed=True, exit_code=0, timed_out=False,
                       requested_cpu_seconds=3600, process_cpu_seconds=3600,
                       process_cpu_nanoseconds=3600*10**9, wall_seconds=3700,
                       iterations=100, completed_exercises=1, corpus_count=len(CORPUS[target]),
                       corpus=[dict(file=f, sha256=HASH, bytes=10) for f in CORPUS[target]],
                       host_font_sha256=HASH if target in ('layout', 'render') else None,
                       binary_sha256=HASH, runtimes={'libexreader.so.1': HASH}, platform='synthetic-only',
                       build_manifest_sha256=digest(proof))
            rows.append(row)

        def check(data, valid=False, edit=None, **options):
            nonlocal checks
            folder = root/str(checks)
            folder.mkdir()
            for i, item in enumerate(data):
                shard = folder/str(i)
                shard.mkdir()
                target = item.get('target') if isinstance(item, dict) else None
                target = target if isinstance(target, str) and target in CORPUS else 'parser'
                (shard/'run.log').write_bytes(logs[target])
                (shard/'last.bin').write_bytes(b'synthetic accounting only')
                (shard/'last.bin.format').write_text('font' if target == 'font' else
                                                     'txt' if target == 'parser' else target+':txt',
                                                     encoding='ascii')
                (shard/'build-manifest.json').write_bytes(proof.read_bytes())
                row = copy.deepcopy(item)
                if isinstance(row, dict):
                    for name, field in [('run.log', 'log_sha256'), ('last.bin', 'last_input_sha256'),
                                        ('last.bin.format', 'last_format_sha256')]:
                        row.setdefault(field, digest(shard/name))
                (shard/'report.json').write_text(json.dumps(row), encoding='utf-8')
            args = SimpleNamespace(reports=folder, output=folder/'summary.json', minimum_cpu_hours=1,
                                   expected_shards=1, expected_source_sha=SOURCE, first_seed=1,
                                   build_manifest=proof)
            for key, value in options.items():
                setattr(args, key, value)
            if edit:
                edit(folder)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    summarize(args)
            except (ValueError, OverflowError):
                assert not valid, 'valid synthetic accounting rejected'
                assert not args.output.exists(), 'invalid accounting produced a summary'
            else:
                assert valid, 'invalid synthetic accounting accepted'
            checks += 1

        check(rows, valid=True)
        check([])
        check(rows[:-1])
        check(rows+[copy.deepcopy(rows[0])])
        check([None, *rows[1:]])
        for field in rows[0]:
            changed = copy.deepcopy(rows)
            del changed[0][field]
            check(changed)
        changes = [
            ('schema', 1), ('source_sha', 'other'), ('source_sha', 'c'*40), ('target', 'unknown'),
            ('target', []), ('working_tree_clean', False), ('source_unchanged', False),
            ('sanitizers_requested', False), ('inputs_unchanged', False), ('passed', False),
            ('exit_code', 1), ('exit_code', False), ('timed_out', True), ('seed', 2), ('seed', -1),
            ('seed', 2**64), ('seed', True), ('effective_seed', True),
            ('process_cpu_seconds', float('nan')), ('process_cpu_seconds', float('inf')),
            ('process_cpu_seconds', 3599), ('process_cpu_nanoseconds', 3600*10**9-1),
            ('requested_cpu_seconds', 0), ('requested_cpu_seconds', True),
            ('iterations', 0), ('completed_exercises', 101), ('corpus_count', 1),
            ('wall_seconds', -1), ('wall_seconds', True), ('corpus', []), ('corpus', [None]),
            ('host_font_sha256', HASH), ('binary_sha256', 'changed'), ('runtimes', {}),
            ('platform', ''), ('build_manifest_sha256', 'c'*64),
            ('sanitizer_environment', {}),
        ]
        for key, value in changes:
            changed = copy.deepcopy(rows)
            changed[0][key] = value
            check(changed)
        for field in ('process_cpu_seconds', 'process_cpu_nanoseconds', 'iterations', 'seed',
                      'requested_cpu_seconds', 'wall_seconds', 'completed_exercises'):
            for value in (None, '1', [], {}):
                changed = copy.deepcopy(rows)
                changed[0][field] = value
                check(changed)
        for name in ('run.log', 'last.bin', 'last.bin.format', 'build-manifest.json'):
            check(rows, edit=lambda folder, name=name: (folder/'0'/name).unlink())
            check(rows, edit=lambda folder, name=name: (folder/'0'/name).write_bytes(b'changed'))
        for name, field, content in [('run.log', 'log_sha256', logs['parser']*2),
                                     ('run.log', 'log_sha256', logs['parser'].replace(b'100 iterations', b'101 iterations')),
                                     ('last.bin.format', 'last_format_sha256', b'font')]:
            def rehash(folder, name=name, field=field, content=content):
                shard = folder/'0'
                (shard/name).write_bytes(content)
                row = json.loads((shard/'report.json').read_text())
                row[field] = digest(shard/name)
                write_json(shard/'report.json', row)
            check(rows, edit=rehash)
        for text in ('{', '[]', '{"schema":2,"schema":2}', '{"schema":NaN}'):
            check(rows, edit=lambda folder, text=text: (folder/'0/report.json').write_text(text))
        for key, value in [('sanitizer_symbols', {}), ('working_tree_clean', False),
                           ('sanitizers_requested', False), ('files', {}), ('files', None),
                           ('source_sha', None), ('schema', True)]:
            changed = copy.deepcopy(manifest)
            changed[key] = value
            write_json(proof, changed)
            changed_rows = copy.deepcopy(rows)
            for row in changed_rows:
                row['build_manifest_sha256'] = digest(proof)
            check(changed_rows)
        write_json(proof, manifest)
        doubled = copy.deepcopy(rows)
        for row in copy.deepcopy(rows):
            row.update(seed=3, effective_seed=3)
            doubled.append(row)
        check(doubled, valid=True, expected_shards=2)
        duplicate = copy.deepcopy(doubled)
        duplicate[-1].update(seed=0, effective_seed=1)
        check(duplicate, expected_shards=2)
        changed = copy.deepcopy(doubled)
        changed[-1]['corpus'][0]['sha256'] = 'c'*64
        check(changed, expected_shards=2)
        check(rows, minimum_cpu_hours=2)
        check(rows, expected_source_sha='c'*40)
        check(rows, first_seed=3)
        check(rows, expected_shards=2)
        check(rows, minimum_cpu_hours=float('nan'))

        # A child timeout must leave a failed report and original output on disk.
        build, fixtures = root/'build', root/'source/tests/fixtures'
        build.mkdir()
        fixtures.mkdir(parents=True)
        for name in CORPUS['parser']:
            path = fixtures/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic-only')
        for name in [binary_name(t) for t in CORPUS]+['CMakeCache.txt', 'libexreader.so.1']:
            (build/name).write_bytes(b'synthetic-only')
        local_manifest = copy.deepcopy(manifest)
        local_manifest['files'] = {p.name: digest(p) for p in build.iterdir()}
        write_json(build/'build-manifest.json', local_manifest)
        args = SimpleNamespace(source=root/'source', build=build, output=root/'timeout',
                               target='parser', seed=1, cpu_seconds=1, wall_seconds=1, require_clean=False)
        raw = b'synthetic child timeout output'
        with patch('run_reliability_campaign.source_state', return_value=(SOURCE, True)), \
             patch('run_reliability_campaign.subprocess.run', side_effect=subprocess.TimeoutExpired('child', 1, output=raw)), \
             contextlib.redirect_stdout(io.StringIO()):
            assert run(args) == 1
        failed = json.loads((args.output/'report.json').read_text())
        assert failed['passed'] is False and failed['timed_out'] is True and failed['process_cpu_seconds'] is None
        assert (args.output/'run.log').read_bytes() == raw
        checks += 1
    print('%d synthetic accounting checks passed' % checks)


if __name__ == '__main__':
    main()

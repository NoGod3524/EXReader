#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check pipeline reachability, exact record routing and process CPU budgets."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def main():
    parser, font, layout, render = map(Path, sys.argv[1:5])
    fixtures = Path(sys.argv[5]);checks = 0

    def run(binary, *args, expected=0):
        nonlocal checks
        result = subprocess.run([str(binary), *map(str, args)], capture_output=True, text=True, timeout=30)
        assert result.returncode == expected, (binary.name, result.returncode, result.stdout, result.stderr)
        counts = re.findall(r'^bounded_chapter_attempts=(\d+) bounded_chapter_completed=(\d+)$',
                            result.stdout, re.M)
        if binary in (layout, render):
            assert len(counts) == 1, (binary.name, 'missing or repeated bounded accounting')
            attempts, completed = map(int, counts[0])
            assert 0 <= completed <= attempts < 2**64
        else:
            assert not counts, (binary.name, 'unexpected bounded accounting')
        checks += 1
        return result.stdout

    def bounded_counts(output):
        return tuple(map(int, re.search(
            r'^bounded_chapter_attempts=(\d+) bounded_chapter_completed=(\d+)$', output, re.M).groups()))

    host = fixtures/'fonts/primary.ttf'
    positive = [(font, fixtures/'fonts/primary.ttf', []),
                (font, fixtures/'fonts/pdf-cubic.otf', []),
                (font, fixtures/'fonts/variable.ttf', []),
                (font, fixtures/'fonts/bitmap.ttf', []),
                (font, fixtures/'fonts/colrv1.ttf', []),
                (font, fixtures/'fonts/colrv1-var.ttf', []),
                (font, fixtures/'fonts/svgfont.ttf', []),
                (layout, fixtures/'layout.epub', ['--font', host]),
                (render, fixtures/'layout.epub', ['--font', host]),
                (render, fixtures/'comic.cbz', ['--font', host]),
                (render, fixtures/'pdf-color/shading-axial.pdf', ['--font', host]),
                (font, fixtures/'font-cff-regression.bin', [])]
    for binary, source, extra in positive:
        output = run(binary, '--replay', source, *extra)
        assert 'status=0' in output
        if binary in (layout, render):
            selected = int(source.suffix == '.epub' and source.stat().st_size % 2 == 0)
            assert bounded_counts(output) == (selected, selected)
            checks += 1
        checks += 1
    with tempfile.TemporaryDirectory(prefix='exreader-pipelines-') as temporary:
        folder = Path(temporary)
        # A harmless trailing byte keeps the ZIP readable while selecting the
        # other EPUB path; both contracts must reach a successful page render.
        alternate=folder/'alternate.epub'
        alternate.write_bytes((fixtures/'layout.epub').read_bytes()+b'\0')
        for binary in (layout,render):
            output = run(binary,'--replay',alternate,'--font',host)
            assert 'status=0' in output
            selected = int(alternate.stat().st_size % 2 == 0)
            assert bounded_counts(output) == (selected, selected)
            checks+=2
        for binary, source, extra in [positive[0], positive[7], positive[9]]:
            saved = folder/(binary.stem+'.bin')
            first = run(binary, '--seed', 17, '--iterations', 100, '--save', saved, *extra, source)
            original = saved.read_bytes();record = Path(str(saved)+'.format').read_bytes()
            assert record.startswith(b'font' if binary == font else b'layout:' if binary == layout else b'render:')
            replay = run(binary, '--replay', saved, *extra)
            assert 'bytes='+str(len(original)) in replay and 'format='+record.decode() in replay
            repeated = run(binary, '--seed', 17, '--iterations', 100, '--save', saved, *extra, source)
            assert original == saved.read_bytes() and record == Path(str(saved)+'.format').read_bytes()
            assert re.search(r'format=.*attempts=.*', first).group() == re.search(r'format=.*attempts=.*', repeated).group()
            if binary in (layout, render):
                assert bounded_counts(first) == bounded_counts(repeated)
                attempts, completed = bounded_counts(replay)
                selected = int(record.endswith(b':epub') and len(original) % 2 == 0)
                assert attempts == selected and completed == int(selected and 'status=0' in replay)
                checks += 2
            run(parser, '--replay', saved, expected=2)
            other = render if binary == layout else layout
            run(other, '--replay', saved, '--font', host, expected=2)
            checks += 4
        saved = folder/'cpu-font.bin'
        output = run(font, '--seed', 1, '--cpu-seconds', 1, '--save', saved, host)
        assert float(re.search(r'process_cpu_seconds=([0-9.]+)', output).group(1)) >= 1
        assert 'requested_cpu_seconds=1' in output
        checks += 2
        run(font, '--cpu-seconds', 0, host, expected=2)
        run(font, '--cpu-seconds', 18446744074, host, expected=2)
        output = run(font, '--seed', 1, '--cpu-seconds', 60, '--iterations', 1, '--save', saved, host)
        assert 'fuzz: 1 iterations over 1 seeds' in output
        assert float(re.search(r'process_cpu_seconds=([0-9.]+)', output).group(1)) < 60
        checks += 2
        for binary in (layout, render):
            output = run(binary, '--seed', 17, '--cpu-seconds', 1,
                         '--save', folder/('cpu-'+binary.stem+'.bin'),
                         '--font', host, fixtures/'layout.epub', alternate)
            attempts, completed = bounded_counts(output)
            assert 0 < completed <= attempts
            assert float(re.search(r'process_cpu_seconds=([0-9.]+)', output).group(1)) >= 1
            assert 'requested_cpu_seconds=1' in output
            checks += 3
    print('%d pipeline checks passed' % checks)


if __name__ == '__main__':
    main()

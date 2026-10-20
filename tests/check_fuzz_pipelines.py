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
        checks += 1
        return result.stdout

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
        assert 'status=0' in run(binary, '--replay', source, *extra)
        checks += 1
    with tempfile.TemporaryDirectory(prefix='exreader-pipelines-') as temporary:
        folder = Path(temporary)
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
    print('%d pipeline checks passed' % checks)


if __name__ == '__main__':
    main()

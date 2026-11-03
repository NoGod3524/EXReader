#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""P acceptance: four one-change controls, baseline lifecycle and real shell exits."""
import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import check_ci_hygiene as guard


def altered(rule):
    text = (ROOT / '.github/workflows/native.yml').read_text(encoding='utf-8')
    if rule == 'packaging':
        return text.replace('python3 tools/build_apple_product.py --sdk stage --target macos', 'echo omitted-product-install --sdk stage --target macos', 1)
    if rule == 'failfast':
        return text.replace(guard.SHELL, 'bash', 1)
    suffix = '          test -n "$sqlite_source"\n' if rule == 'diagnostic' else '          set +e\n          python -c "raise SystemExit(2)"\n          echo silently continued\n'
    return text + '  injected-control:\n    runs-on: ubuntu-22.04\n    defaults:\n      run:\n        shell: ' + guard.SHELL + '\n    steps:\n      - run: |\n' + suffix


def shell_controls(rule):
    bash = shutil.which('bash')
    if not bash and os.name == 'nt':
        git = shutil.which('git')
        bash = str(Path(git).resolve().parents[1] / 'bin/bash.exe') if git else None
    if not bash or not Path(bash).exists():
        raise RuntimeError('Bash is required for runtime exit-status controls')
    with tempfile.TemporaryDirectory(prefix='exr-ci-shell-') as directory:
        step = Path(directory) / 'step.sh'
        marker = Path(directory) / 'continued'
        cases = {
            'failfast': ('python -c "raise SystemExit(37)"\necho continued > "' + marker.as_posix() + '"\n', 37, 'actual=exit 37'),
            'diagnostic': ('ci_require_nonempty "" "SOURCE_DIR from CMakeCache" build/provider/CMakeCache.txt build/stage\n', 1, 'actual=<empty>'),
            'negative': ('ci_expect_failure python -c "import sys; print(\'rejected-object: bad archive\', file=sys.stderr); sys.exit(9)"\n', 0, 'rejected-object: bad archive'),
        }
        if rule not in cases:
            return
        body, expected, message = cases[rule]
        step.write_text(body, encoding='utf-8', newline='\n')
        result = subprocess.run([bash, '.github/scripts/ci.sh', step.as_posix()], cwd=ROOT, capture_output=True, text=True)
        output = result.stdout + result.stderr
        assert result.returncode == expected, output
        assert message in output and not marker.exists(), output
        print(output, end='')
        if rule == 'negative':
            step.write_text('ci_expect_failure python -c "print(\'unexpected acceptance\')"\n', encoding='utf-8')
            result = subprocess.run([bash, '.github/scripts/ci.sh', step.as_posix()], cwd=ROOT, capture_output=True, text=True)
            assert result.returncode == 1 and 'control did not fail' in result.stdout + result.stderr
            print(result.stdout + result.stderr, end='')
    print('PASS: runtime ' + rule)


def baseline_controls(fault):
    with tempfile.TemporaryDirectory(prefix='exr-ci-baseline-') as directory:
        root = Path(directory)
        file = '.github/workflows/probe.yml'
        path = root / file
        path.parent.mkdir(parents=True)
        (root / 'tools').mkdir()
        original = 'on: workflow_dispatch\njobs:\n  probe:\n    runs-on: ubuntu-22.04\n    steps:\n      - run: test -n "$source"\n'
        path.write_text(original, encoding='utf-8')
        row = {'file': file, 'line': 6, 'pattern': 'diagnostic', 'line_sha256': guard.line_sha(original.splitlines()[5])}
        manifest = root / guard.BASELINE
        manifest.write_text(json.dumps([row]), encoding='utf-8')
        def git(*args):
            return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.STDOUT, text=True).strip()
        git('init', '-q')
        git('add', '.')
        git('-c', 'user.name=CI probe', '-c', 'user.email=ci-probe@example.invalid', '-c', 'core.autocrlf=false', 'commit', '-qm', 'baseline fixture')
        base = git('rev-parse', 'HEAD')
        def verify(label, failure):
            output = io.StringIO()
            with redirect_stdout(output):
                result = guard.check(root, base, 'diagnostic')
            assert result == int(failure), output.getvalue()
            print('PASS: ' + label)
            if failure:
                print('\n'.join(line for line in output.getvalue().splitlines() if line.startswith('ERROR:')))
            if fault == {'new violation rejected': 'baseline-new', 'modified baseline line rejected': 'baseline-modified', 'fixed line with stale baseline rejected': 'baseline-stale'}.get(label):
                print('Injected baseline control returns the actual checker exit 1')
                raise SystemExit(result)
        verify('unchanged historical line retained', False)
        path.write_text(original + '      - run: test -n "$new"\n', encoding='utf-8')
        verify('new violation rejected', True)
        path.write_text(original.replace('$source', '$modified'), encoding='utf-8')
        verify('modified baseline line rejected', True)
        path.write_text(original.replace('test -n "$source"', 'echo fixed'), encoding='utf-8')
        verify('fixed line with stale baseline rejected', True)
        manifest.write_text('[]', encoding='utf-8')
        verify('fixed line and removed baseline accepted', False)
        path.write_text('\n' + original, encoding='utf-8')
        row['line'] = 7
        manifest.write_text(json.dumps([row]), encoding='utf-8')
        verify('moved line cannot be re-waived', True)
        path.write_text(original + '      - run: test -n "$new"\n', encoding='utf-8')
        row['line'] = 6
        extra = dict(row, line=7, line_sha256=guard.line_sha(path.read_text().splitlines()[6]))
        manifest.write_text(json.dumps([row, extra]), encoding='utf-8')
        verify('new violation cannot be registered into baseline', True)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rule', choices=guard.RULES, required=True)
    parser.add_argument('--fault', choices=('none', *guard.RULES, 'baseline-new', 'baseline-modified', 'baseline-stale'), default='none')
    args = parser.parse_args()
    name = '.github/workflows/native.yml'
    clean = (ROOT / name).read_text(encoding='utf-8')
    assert not guard.issues(name, clean, args.rule), 'native workflow violates the selected rule'
    bad = guard.issues(name, altered(args.rule), args.rule)
    assert bad, args.rule + ': one-change negative was accepted'
    if args.fault == args.rule:
        print('Injected one change into a temporary copy of native.yml; repository unchanged')
        for _, _, message in bad:
            print('ERROR: ' + message)
        return 1
    print('PASS: clean workflow accepted; one-change ' + args.rule + ' control rejected')
    shell_controls(args.rule)
    if args.rule == 'diagnostic':
        baseline_controls(args.fault)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

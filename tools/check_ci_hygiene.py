#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check CI run steps; --base gates changed steps and reports existing debt."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
RULES = ('packaging', 'failfast', 'diagnostic', 'negative')
SHELL = 'bash .github/scripts/ci.sh {0}'
BASELINE = 'tools/ci_hygiene_baseline.json'


def load(text):
    return yaml.load(text, Loader=yaml.BaseLoader) or {}


def steps(document):
    result = []
    default = document.get('defaults', {}).get('run', {}).get('shell', '')
    for job_id, job in document.get('jobs', {}).items():
        shell = job.get('defaults', {}).get('run', {}).get('shell', default)
        for index, step in enumerate(job.get('steps', [])):
            if 'run' in step:
                result.append((job_id, index, step, step.get('shell', shell)))
    return result


def run_locations(text):
    node = yaml.compose(text, Loader=yaml.BaseLoader)
    def mapping(value):
        return {k.value: v for k, v in value.value}
    result = {}
    for job, value in mapping(mapping(node)['jobs']).items():
        for index, step in enumerate(mapping(value).get('steps', yaml.SequenceNode('tag:yaml.org,2002:seq', [])).value):
            fields = mapping(step)
            if 'run' in fields:
                value = fields['run']
                result[job, index] = value.start_mark.line + (2 if value.style in ('|', '>') else 1)
    return result


def issues(path, text, selected=None, added=()):
    document = load(text)
    result = []
    locations = run_locations(text)
    for job, index, step, shell in steps(document):
        body = step['run']
        start = locations[job, index]
        key = (job, step.get('name', ''), body, shell, step.get('continue-on-error', 'false'))

        def error(rule, detail, expected, offset=0):
            if selected is None or rule == selected:
                message = f'[{rule}] expected={expected}; actual={detail}; candidate={path} jobs.{job}.steps[{index}]'
                result.append(((path, start + offset, rule), rule, f'{path}:{start + offset} {message}'))
                if rule in ('failfast', 'negative'):
                    for number in sorted(set(added) & set(range(start, start + len(body.splitlines())))):
                        if number != start + offset:
                            result.append(((path, number, rule), rule, f'{path}:{number} {message}'))

        if step.get('continue-on-error') == 'true':
            error('failfast', 'continue-on-error=true', 'unhandled failures stop the job')
        commands = [line for line in body.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        needs_strict = len(commands) > 1 or bool(re.search(r'[;|]', body))
        if shell != SHELL and needs_strict:
            if shell.startswith(('pwsh', 'powershell')):
                if "$ErrorActionPreference = 'Stop'" not in body or '$PSNativeCommandUseErrorActionPreference = $true' not in body:
                    error('failfast', 'PowerShell native exit status is not fail-fast', 'Stop + PSNativeCommandUseErrorActionPreference=true')
            elif not re.fullmatch(r'set -[A-Za-z]*e[A-Za-z]*u[A-Za-z]*o pipefail', commands[0].strip()):
                error('failfast', f'shell={shell or "runner default"} without strict preamble', SHELL + ' or explicit set -euo pipefail')
        if re.search(r'\|\|\s*(?:true|:)\s*(?:$|;)', body, re.M):
            error('failfast', 'failure swallowed by || true/:', 'preserve the first unhandled nonzero exit')
        for offset, line in enumerate(body.splitlines()):
            if re.search(r'(?:^|;)\s*(?:test\s+-n\b|\[\s+-n\b)', line):
                if not ('||' in line and all(word in line.lower() for word in ('expected', 'actual', 'candidate'))):
                    error('diagnostic', line.strip(), 'nonempty check prints expected / actual / candidate paths (or ci_require_nonempty)', offset)
        if re.search(r'\bset\s+\+e\b', body):
            required = (r'rc=\$\?', r'set -e\b', r'\[\s*"\$rc"\s+-ne\s+0\s*\]\s*\|\|', 'control did not fail')
            if not all(re.search(pattern, body) for pattern in required):
                error('negative', 'incomplete expected-failure wrapper', 'set +e; command; rc=$?; set -e; [ "$rc" -ne 0 ] || fail')
            elif re.search(r'(?:>|&>)[^\n]*[/\\]dev[/\\]null', body) or ('2>&1' in body and not re.search(r'\bcat\b', body)):
                error('negative', 'rejected command diagnostics are hidden', 'print actual stdout/stderr of the rejected command')
        if re.search(r'^\s*(?:if\s+!\s+|!\s+)(?:cmake|ctest|python[0-9]*|\./)', body, re.M):
            error('negative', 'implicit expected failure loses the actual status', 'ci_expect_failure or explicit rc capture with visible error')
    if selected is None or selected == 'packaging':
        for job_id, job in document.get('jobs', {}).items():
            installed = set()
            for index, step in enumerate(job.get('steps', [])):
                body = step.get('run', '')
                # Match explicit SDK prefixes and the native workflow's two-target loop.
                for line in body.splitlines():
                    product = re.search(r'\btools/build_apple_product\.py\s+.*?--sdk\s+[\"\']?([^\s\"\']+)', line)
                    if product:
                        value = product[1]
                        installed.update((value.replace('$sdk', target) for target in ('iphoneos', 'iphonesimulator')) if '$sdk' in value else (value,))
                    host = re.search(r'\btools/build_apple_host\.py\s+.*?--sdk\s+[\"\']?([^\s\"\']+)', line)
                    if host and host[1] not in installed:
                        number = locations[job_id, index] + body.splitlines().index(line)
                        key = (path, number, 'packaging')
                        actual = ', '.join(sorted(installed)) or '<none>'
                        result.append((key, 'packaging', f'{path}:{number} [packaging] expected=product install before host for SDK {host[1]}; actual=installed prefixes {actual}; candidate={host[1]}/include/exreader-product and {host[1]}/lib in jobs.{job_id}.steps[{index}]'))
    return result


def added_lines(root, base):
    diff = subprocess.check_output(['git', '-C', str(root), 'diff', '--no-ext-diff', '--no-renames', '-U0', base, '--', '.github/workflows'], text=True)
    result = {}
    name = None
    for line in diff.splitlines():
        if line.startswith('+++ b/'):
            name = line[6:]
        elif name and line.startswith('@@'):
            match = re.search(r'\+(\d+)(?:,(\d+))? @@', line)
            start, count = int(match[1]), int(match[2] or 1)
            result.setdefault(name, set()).update(range(start, start + count))
    # Untracked new workflow files are not included in git diff.
    tracked = set(subprocess.check_output(['git', '-C', str(root), 'ls-files', '.github/workflows'], text=True).splitlines())
    for path in (root / '.github/workflows').glob('*.y*ml'):
        name = path.relative_to(root).as_posix()
        if name not in tracked:
            result[name] = set(range(1, len(path.read_text(encoding='utf-8').splitlines()) + 1))
    return result


def line_sha(line):
    return hashlib.sha256(line.encode('utf-8')).hexdigest()


def check(root, base=None, selected=None):
    errors = 0
    debt = Counter()
    added = added_lines(root, base) if base else {}
    rows = json.loads((root / BASELINE).read_text(encoding='utf-8'))
    allowed = {}
    previous = []
    frozen = False
    if base:
        old = subprocess.run(['git', '-C', str(root), 'show', f'{base}:{BASELINE}'], capture_output=True)
        if old.returncode == 0:
            frozen = True
            previous = json.loads(old.stdout)
    for row in rows:
        key = (row['file'], row['line'], row['pattern'])
        if selected and row['pattern'] in RULES and row['pattern'] != selected:
            continue
        name, number, rule = key
        path = root / name
        reason = None
        if not isinstance(number, int) or rule not in RULES or not name.startswith('.github/workflows/') or Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name:
            reason = 'invalid exact baseline location/pattern'
        elif key in allowed:
            reason = 'duplicate baseline entry'
        elif not path.is_file():
            reason = 'baseline file missing; remove stale entry'
        else:
            lines = path.read_text(encoding='utf-8').splitlines()
            if not 1 <= number <= len(lines):
                reason = 'baseline line missing; remove stale entry'
            elif line_sha(lines[number - 1]) != row['line_sha256']:
                reason = 'baseline line hash changed; fix the touched step and remove its entry'
            elif number in added.get(name, ()):
                reason = 'baseline cannot exempt an added/modified/moved line from git diff -U0'
            elif any(old['file'] == name and old['pattern'] == rule and old['line_sha256'] == row['line_sha256'] and old['line'] != number for old in previous):
                reason = 'moved baseline line cannot acquire a new waiver'
            elif frozen and row not in previous:
                reason = 'baseline may shrink only; new or rewritten waiver rejected'
        if reason:
            print(f'ERROR: {name}:{number} [{rule}] expected=unchanged live exact baseline; actual={reason}; candidate={BASELINE}')
            errors += 1
        else:
            allowed[key] = row
    seen = set()
    for path in sorted((root / '.github/workflows').glob('*.y*ml')):
        name = path.relative_to(root).as_posix()
        for key, rule, message in issues(name, path.read_text(encoding='utf-8'), selected, added.get(name, ())):
            if key in seen:
                continue
            seen.add(key)
            if key in allowed:
                debt[rule] += 1
                print('EXISTING: ' + message)
            else:
                errors += 1
                print('ERROR: ' + message)
    for key in allowed.keys() - seen:
        name, number, rule = key
        print(f'ERROR: {name}:{number} [{rule}] expected=live violation for baseline entry; actual=no match (fixed or disappeared); candidate={BASELINE}; remove stale entry')
        errors += 1
    print(f'{"FAIL" if errors else "PASS"}: CI hygiene; violations={errors}; existing debt={dict(debt)}')
    return int(bool(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', help='PR base SHA for added-line detection (git diff -U0)')
    parser.add_argument('--rule', choices=RULES)
    args = parser.parse_args()
    if args.base:
        subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--verify', args.base + '^{commit}'], check=True, stdout=subprocess.DEVNULL)
    return check(ROOT, args.base, args.rule)


if __name__ == '__main__':
    raise SystemExit(main())

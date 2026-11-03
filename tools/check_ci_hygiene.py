#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check CI run steps; --base gates changed steps and reports existing debt."""
import argparse
from collections import Counter
from datetime import datetime, timezone
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
                effective = step.get('shell', shell)
                runner = job.get('runs-on', '')
                windows = isinstance(runner, str) and runner.lower().startswith('windows')
                windows = windows or bool(re.search(r"runner\.os\s*==\s*['\"]Windows['\"]", step.get('if', ''), re.I))
                if not effective and windows:
                    effective = 'pwsh'  # Actions default on a known Windows runner.
                result.append((job_id, index, step, effective))
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


def command_shape(body):
    """Count shell commands, not Python/heredoc payload or quoted punctuation."""
    commands, pending, current = [], [], ''
    for line in body.splitlines():
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        here = re.findall(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z_0-9]*)['\"]?", line)
        pending.extend(here)
        line = re.sub(r"<<-?\s*['\"]?[A-Za-z_][A-Za-z_0-9]*['\"]?", ' HEREDOC ', line)
        current += line.rstrip().removesuffix('\\') + ' '
        if line.rstrip().endswith('\\'):
            continue
        commands.append(current.strip())
        current = ''
    if current.strip():
        commands.append(current.strip())
    compound = False
    for command in commands:
        # Quoted Python -c programs, regexes and strings are arguments.
        masked = re.sub(r"'(?:[^']*)'|\"(?:\\.|[^\"\\])*\"", ' ARG ', command)
        masked = re.sub(r'\$\{\{.*?\}\}', ' EXPR ', masked)
        masked = masked.split('#', 1)[0]
        if re.search(r'\|(?!=)|&&|;|\$\(|`|^\s*(?:for|while|until|if|case|select)\b', masked):
            compound = True
    return commands, len(commands) > 1 or compound


def shell_branch(shell):
    if shell.strip() == 'bash':
        return 'explicit_bash'
    if shell.startswith(('pwsh', 'powershell')):
        return 'powershell'
    if not shell:
        return 'default_bash'
    return 'custom'


def shell_problem(shell, body):
    """Use the Actions shell invocation, not the presence of a stylistic preamble."""
    branch = shell_branch(shell)
    commands, compound = command_shape(body)
    if branch == 'explicit_bash' or shell == SHELL:
        return None  # Actions bash: --noprofile --norc -e -o pipefail {0}.
    if branch == 'powershell':
        stop = re.search(r"\$ErrorActionPreference\s*=\s*['\"]Stop['\"]", body, re.I)
        native = re.search(r'\$PSNativeCommandUseErrorActionPreference\s*=\s*\$true\b', body, re.I)
        return None if stop and native else 'PowerShell requires Stop and native error propagation'
    if not compound:
        return None  # One command propagates its own status under bash -e.
    if commands and re.fullmatch(r'set -[A-Za-z]*e[A-Za-z]*u[A-Za-z]*o pipefail', commands[0].strip()):
        return None
    if branch == 'custom' and shell.startswith('bash ') and re.search(r'\s-[A-Za-z]*e[A-Za-z]*\b', shell) and re.search(r'(?:-o\s+pipefail|-[A-Za-z]*o\s+pipefail)', shell):
        return None
    return f'{branch} multi-command block lacks strict shell/preamble'


def content_locations(text):
    """One-based occurrence among all identical physical lines in this file."""
    counts = Counter()
    result = {}
    for number, line in enumerate(text.splitlines(), 1):
        digest = line_sha(line)
        counts[digest] += 1
        result[number] = (digest, counts[digest])
    return result


def baseline_key(row):
    return row['file'], row['content_sha256'], row['occurrence']


def normalise_baseline(rows, text_for):
    """Read both the frozen legacy format and the new content-key format."""
    result = {}
    for row in rows:
        if 'content_sha256' in row:
            key = baseline_key(row)
            patterns = row['patterns']
            if key in result:
                raise ValueError('duplicate content identity')
        else:
            locations = content_locations(text_for(row['file']))
            digest, occurrence = locations[row['line']]
            if digest != row['line_sha256']:
                raise ValueError('legacy content differs from its frozen hash')
            key = (row['file'], digest, occurrence)
            patterns = [row['pattern']]
        result.setdefault(key, set()).update(patterns)
    return result


def write_baseline(root, mapping, command):
    rows = [dict(file=name, content_sha256=digest, occurrence=occurrence, patterns=sorted(patterns))
            for (name, digest, occurrence), patterns in mapping.items()]
    data = '[\n' + ',\n'.join('  ' + json.dumps(row) for row in rows) + '\n]\n'
    (root / BASELINE).write_text(data, encoding='utf-8', newline='\n')
    metadata = {'schema': 2, 'identity': ['file', 'content_sha256', 'occurrence'],
                'generated_date_utc': datetime.now(timezone.utc).date().isoformat(),
                'source_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
                'command': command, 'entries': len(rows),
                'rule_bindings': sum(len(row['patterns']) for row in rows),
                'checker_sha256': hashlib.sha256((root / 'tools/check_ci_hygiene.py').read_bytes()).hexdigest(),
                'baseline_sha256': hashlib.sha256(data.encode()).hexdigest(),
                'patterns': dict(Counter(rule for row in rows for rule in row['patterns']))}
    (root / 'tools/ci_hygiene_baseline.meta.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8', newline='\n')
    return metadata


def remap_baseline(root):
    rows = json.loads((root / BASELINE).read_text(encoding='utf-8'))
    mapping, unmapped = {}, []
    texts = {}
    for row in rows:
        try:
            name = row['file']
            if name not in texts:
                texts[name] = (root / name).read_text(encoding='utf-8')
            converted = normalise_baseline([row], texts.__getitem__)
            for key, patterns in converted.items():
                mapping.setdefault(key, set()).update(patterns)
        except (KeyError, ValueError, OSError) as error:
            unmapped.append({'entry': row, 'reason': str(error)})
    report = {'before_entries': len(rows), 'after_content_identities': len(mapping),
              'after_rule_bindings': sum(map(len, mapping.values())),
              'identity_count_difference': len(mapping) - len(rows), 'unmapped': unmapped,
              'combined_rule_identities': [dict(file=k[0], content_sha256=k[1], occurrence=k[2], patterns=sorted(v))
                                           for k, v in mapping.items() if len(v) > 1]}
    if not unmapped:
        report['metadata'] = write_baseline(root, mapping, 'python tools/check_ci_hygiene.py --remap-baseline')
    target = root / 'evidence/final-gate-probe-20261103/baseline-remap.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report))
    return int(bool(unmapped))


def emit_baseline(root):
    mapping = {}
    for path in sorted((root / '.github/workflows').glob('*.y*ml')):
        text = path.read_text(encoding='utf-8')
        locations = content_locations(text)
        for (name, line, rule), _, _ in issues(path.relative_to(root).as_posix(), text):
            digest, occurrence = locations[line]
            mapping.setdefault((name, digest, occurrence), set()).add(rule)
    print(json.dumps(write_baseline(root, mapping, 'python tools/check_ci_hygiene.py --emit-baseline')))
    return 0


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
        problem = shell_problem(shell, body)
        if problem:
            error('failfast', problem + f'; shell={shell or "runner default bash -e"}', 'Actions explicit bash, strict default-shell preamble, or PowerShell error propagation')
        commands, _ = command_shape(body)
        for command in commands:
            masked = re.sub(r"'(?:[^']*)'|\"(?:\\.|[^\"\\])*\"", ' ARG ', command)
            if re.search(r'\|\|\s*(?:true|:)\s*(?:$|;)|;\s*:\s*(?:$|;)', masked):
                error('failfast', 'failure swallowed by || true/: or ; :', 'preserve the first unhandled nonzero exit')
                break
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
    """New content occurrences only: moving an unchanged line is not new debt."""
    changed = set(subprocess.check_output(['git', '-C', str(root), 'diff', '--no-ext-diff', '--no-renames', '--name-only', base, '--', '.github/workflows'], text=True).splitlines())
    tracked = set(subprocess.check_output(['git', '-C', str(root), 'ls-files', '.github/workflows'], text=True).splitlines())
    changed.update(p.relative_to(root).as_posix() for p in (root / '.github/workflows').glob('*.y*ml') if p.relative_to(root).as_posix() not in tracked)
    result = {}
    for name in changed:
        path = root / name
        if not path.is_file():
            continue
        old = subprocess.run(['git', '-C', str(root), 'show', f'{base}:{name}'], capture_output=True)
        previous = set(content_locations(old.stdout.decode('utf-8')).values()) if old.returncode == 0 else set()
        result[name] = {number for number, key in content_locations(path.read_text(encoding='utf-8')).items() if key not in previous}
    return result


def line_sha(line):
    return hashlib.sha256(line.encode('utf-8')).hexdigest()


def check(root, base=None, selected=None):
    errors, debt = 0, Counter()
    added = added_lines(root, base) if base else {}
    rows = json.loads((root / BASELINE).read_text(encoding='utf-8'))
    previous, frozen, base_texts = {}, False, {}
    if base:
        old = subprocess.run(['git', '-C', str(root), 'show', f'{base}:{BASELINE}'], capture_output=True)
        if old.returncode == 0:
            frozen = True
            def base_text(name):
                if name not in base_texts:
                    base_texts[name] = subprocess.check_output(['git', '-C', str(root), 'show', f'{base}:{name}']).decode('utf-8')
                return base_texts[name]
            try:
                previous = normalise_baseline(json.loads(old.stdout), base_text)
            except (KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
                print(f'ERROR: {BASELINE}:1 expected=valid frozen base; actual={error}')
                return 1
    allowed, files, locations, declared = {}, {}, {}, set()
    for row in rows:
        name = row.get('file', '')
        reason, number = None, 1
        try:
            key = baseline_key(row)
            if key in declared:
                raise ValueError('duplicate content identity')
            declared.add(key)
            patterns = row['patterns']
            if not isinstance(patterns, list) or not patterns or len(set(patterns)) != len(patterns) or not set(patterns) <= set(RULES):
                raise ValueError('invalid rule obligations')
            if selected and selected not in patterns:
                continue
            if not name.startswith('.github/workflows/') or Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name:
                raise ValueError('invalid exact baseline file')
            if not re.fullmatch('[0-9a-f]{64}', key[1]) or type(key[2]) is not int or key[2] < 1:
                raise ValueError('invalid content hash/occurrence')
            if key in allowed:
                raise ValueError('duplicate content identity')
            if name not in files:
                files[name] = (root / name).read_text(encoding='utf-8')
                locations[name] = {value: line for line, value in content_locations(files[name]).items()}
            number = locations[name].get(key[1:], 1)
            if key[1:] not in locations[name]:
                raise ValueError('baseline content occurrence missing; remove stale entry')
            if frozen and (key not in previous or not set(patterns) <= previous[key]):
                raise ValueError('baseline may shrink only; new content/rule waiver rejected')
            allowed[key] = set(patterns) & ({selected} if selected else set(RULES))
        except (KeyError, TypeError, ValueError, OSError) as error:
            reason = str(error)
        if reason:
            print(f'ERROR: {name}:{number} expected=live exact content identity; actual={reason}; candidate={BASELINE}')
            errors += 1
    seen = set()
    for path in sorted((root / '.github/workflows').glob('*.y*ml')):
        name = path.relative_to(root).as_posix()
        text = path.read_text(encoding='utf-8')
        identities = content_locations(text)
        for (file, number, rule), _, message in issues(name, text, selected, added.get(name, ())):
            key = (file, *identities[number])
            obligation = (key, rule)
            if obligation in seen:
                continue
            seen.add(obligation)
            if rule in allowed.get(key, set()):
                debt[rule] += 1
                print('EXISTING: ' + message)
            else:
                errors += 1
                print('ERROR: ' + message)
    for key, patterns in allowed.items():
        for rule in patterns:
            if (key, rule) not in seen:
                number = locations[key[0]][key[1:]]
                print(f'ERROR: {key[0]}:{number} [{rule}] expected=live violation; actual=no match (fixed/disappeared); candidate={BASELINE}; remove stale entry')
                errors += 1
    print(f'{"FAIL" if errors else "PASS"}: CI hygiene; violations={errors}; existing debt={dict(debt)}')
    return int(bool(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', help='PR base SHA for added-line detection (git diff -U0)')
    parser.add_argument('--rule', choices=RULES)
    parser.add_argument('--remap-baseline', action='store_true', help='Map existing debt only to content identities; do not admit new violations')
    parser.add_argument('--emit-baseline', action='store_true', help='Explicit owner-approved regeneration; never run automatically in CI')
    args = parser.parse_args()
    if args.remap_baseline:
        return remap_baseline(ROOT)
    if args.emit_baseline:
        return emit_baseline(ROOT)
    if args.base:
        subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--verify', args.base + '^{commit}'], check=True, stdout=subprocess.DEVNULL)
    return check(ROOT, args.base, args.rule)


if __name__ == '__main__':
    raise SystemExit(main())

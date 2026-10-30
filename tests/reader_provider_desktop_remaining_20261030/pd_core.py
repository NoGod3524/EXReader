"""C09 Windows/macOS final-program provider audit core. Execution: GitHub Actions only.

Evidence binds to one exact source/run/attempt/platform. Nothing here grants F07 or six-platform
acceptance; every result writes the acceptance flags as False.
"""
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/reader_final_provider_20261030'))
import fp_maps as M  # noqa: E402  (read-only reuse of the C05 ownership policy)

REPO = 'NoGod3524/EXReader'
BASE = '441a5ae2653dcbeef7a25b3e38c7a7adee12911f'
BRANCH = 'claude/dot-c09-provider-desktop-20261030'
OWNED = 'tests/reader_provider_desktop_remaining_20261030/'
WORKFLOW = '.github/workflows/claude_c09_provider_desktop_20261030.yml'
AUDITOR = 'scripts/audit/claude_c09_provider_desktop_20261030.py'
DOC = 'docs/reader-total-progress/CLAUDE_C09_PROVIDER_DESKTOP_20261030.md'
OUT = ROOT / 'build/provider-desktop'
PLATFORMS = ('windows', 'macos')
ACCEPT_FLAGS = ('f07_accepted', 'full_six_platform_f07_accepted')


def require(value, message):
    if not value:
        raise ValueError(message)


def actions_only():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions only')
    require(os.environ.get('GITHUB_REPOSITORY') == REPO, 'wrong repository')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=_jsonable) + '\n', encoding='utf-8')


def _jsonable(value):
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError('not serialisable: %r' % (value,))


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def identity(platform=None, sdk_version=None):
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'], base_sha=BASE, platform=platform,
                sdk_version=sdk_version, runner_os=os.environ.get('RUNNER_OS'))


def owned_paths(changes):
    """Additions-only scope: tests dir, workflow, auditor, doc. Anything else is rejected."""
    for line in changes:
        status, path = line.split('\t')
        require(status == 'A' and (path.startswith(OWNED) or path in (WORKFLOW, AUDITOR, DOC)),
                'only new owned files allowed: ' + line)
    return changes


def guard():
    actions_only()
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH, 'dedicated branch only')
    require(git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'checkout identity')
    git('merge-base', '--is-ancestor', BASE, 'HEAD')
    changes = git('diff', '--name-status', '--no-renames', BASE, 'HEAD').splitlines()
    require(changes, 'no owned source changes')
    owned_paths(changes)
    require(not git('status', '--porcelain', '--untracked-files=no'), 'tracked source dirty')
    return dict(identity(), changed=changes, source_scope_passed=True)


def norm(path, fold=False):
    text = os.path.normpath(str(path)).replace(chr(92), '/')
    return text.lower() if fold else text


def library_identities(roots, suffixes, fold=False):
    """Every installed library file under the role roots: path, role, size, sha256."""
    rows = []
    for role, base in roots:
        base = Path(base)
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*')):
            if path.is_file() and path.suffix.lower() in suffixes:
                rows.append(dict(path=norm(path, fold), role=role, size=path.stat().st_size, sha256=digest(path)))
    return rows


def as_sets(evidence):
    copy_ = dict(evidence)
    copy_['archives'] = {a: {m: {k: set(v) for k, v in row.items()} for m, row in t.items()}
                         for a, t in evidence['archives'].items()}
    return copy_


def policy(evidence, canon=lambda s: s):
    """Provider findings: the C05 ownership policy plus final-image dynamic rules."""
    findings = M.audit(as_sets(evidence), canon) + [dict(f) for f in evidence.get('extra_findings', [])]
    for name in evidence.get('dynamic_needed', []):
        low = name.lower()
        if 'sqlite' in low and not any(f.get('name') == name for f in findings):
            findings.append(dict(kind='system_sqlite_dependency', name=name))
    for row in evidence.get('dynamic_imports', []):
        if canon(row['symbol']).startswith('sqlite3'):
            findings.append(dict(kind='dynamic_sqlite_import', symbol=row['symbol'], library=row.get('library')))
    for row in evidence.get('runtime_identity', []):
        if row.get('status') == 'mismatch':
            findings.append(dict(kind='sdk_runtime_identity_mismatch', **{k: row[k] for k in row if k != 'status'}))
    for name in evidence.get('forbidden_dynamic_sdk', []):
        if any(name.lower() == n.lower() or name.lower() in n.lower() for n in evidence.get('dynamic_needed', [])):
            findings.append(dict(kind='second_sdk_provider_dynamic', name=name))
    return findings


def kinds(findings):
    counts = {}
    for f in findings:
        counts[f['kind']] = counts.get(f['kind'], 0) + 1
    return counts


def negative_controls(evidence, canon=lambda s: s):
    """Run mutated copies of the REAL evidence; each must raise the expected finding kind."""
    base = kinds(policy(evidence, canon))
    roles = evidence['roles']
    entry = canon('sqlite3_open_v2')
    owner = None
    for archive, member in evidence['selected']:
        row = evidence['archives'].get(archive, {}).get(member)
        if row and any(canon(s) == entry for s in row['defined']):
            owner = (archive, member)
            break
    controls = []

    def run(name, expected, mutate):
        sample = copy.deepcopy(evidence)
        try:
            mutate(sample)
            after = kinds(policy(sample, canon))
            hit = after.get(expected, 0) > base.get(expected, 0)
            controls.append(dict(name=name, expected_kind=expected, observed=after, rejected=hit))
        except Exception as error:  # a control that cannot even be built is a failed control
            controls.append(dict(name=name, expected_kind=expected, rejected=False, error=str(error)))

    def swap_roles(sample):
        sdk, product = sample['roles'].get('sdk', []), sample['roles'].get('product', [])
        sample['roles']['sdk'], sample['roles']['product'] = product, sdk

    def foreign_sqlite(sample):
        sdk_root = sample['roles']['sdk'][0]
        fake = sdk_root + 'lib/wrong-sdk-sqlite'
        sample['archives'][fake] = {'vendor_sqlite': dict(defined=[entry], weak=[], undefined=[])}
        sample['selected'].append([fake, 'vendor_sqlite'])

    def duplicate_product(sample):
        require(owner, 'no real sqlite owner to duplicate')
        fake = sample['roles']['product'][0] + 'lib/duplicate-provider'
        sample['archives'][fake] = {'duplicate': copy.deepcopy(sample['archives'][owner[0]][owner[1]])}
        sample['selected'].append([fake, 'duplicate'])

    def drop_owner(sample):
        require(owner, 'no real sqlite owner to remove')
        sample['selected'] = [x for x in sample['selected'] if tuple(x) != owner]

    def unowned(sample):
        fake = '/unowned-root/other-provider'
        sample['archives'][fake] = {'x': dict(defined=['not_a_symbol'], weak=[], undefined=[])}
        sample['selected'].append([fake, 'x'])

    def system_sqlite(sample):
        sample['dynamic_needed'] = list(sample.get('dynamic_needed', [])) + ['libsqlite3.dylib' if evidence['platform'] == 'macos' else 'sqlite3.dll']

    def wrong_runtime(sample):
        sample['runtime_identity'] = list(sample.get('runtime_identity', [])) + [
            dict(status='mismatch', name='wrong-sdk-runtime', expected_sha256='0' * 64, actual_sha256='f' * 64)]

    def second_sdk(sample):
        sample['forbidden_dynamic_sdk'] = ['exreader']
        sample['dynamic_needed'] = list(sample.get('dynamic_needed', [])) + ['exreader.dll']

    run('wrong_sdk_role_swap', 'sqlite_not_uniquely_product_catalog', swap_roles)
    run('wrong_sdk_foreign_sqlite_provider', 'foreign_sqlite_provider', foreign_sqlite)
    run('duplicate_provider_real_member', 'duplicate_provider', duplicate_product)
    run('missing_sqlite_owner', 'sqlite_not_uniquely_product_catalog', drop_owner)
    run('unowned_link_input', 'unowned_link_input', unowned)
    run('system_sqlite_dependency', 'system_sqlite_dependency', system_sqlite)
    run('wrong_sdk_runtime_identity', 'sdk_runtime_identity_mismatch', wrong_runtime)
    if evidence['platform'] == 'windows':
        run('second_dynamic_sdk_provider', 'second_sdk_provider_dynamic', second_sdk)
    return controls

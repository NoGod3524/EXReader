"""Final-image provider/map audit core (package C05). Execution: GitHub Actions only.

Evidence is bound to one exact source/run/attempt/platform/SDK/provider identity.
Nothing here grants F07 or six-platform acceptance by itself.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REPO = 'NoGod3524/EXReader'
BASE = 'c46f7036d81f88d8529871590f780b5430630e47'
BRANCH = 'claude/dot-f07-provider-20261030'
OWNED = 'tests/reader_final_provider_20261030/'
WORKFLOW = '.github/workflows/claude_dot_f07_provider_20261030.yml'
AUDITOR = 'scripts/audit/claude_dot_f07_provider_20261030.py'
DOC = 'docs/reader-total-progress/CLAUDE_DOT_C05_20261030.md'
OUT = ROOT / 'build/final-provider'
PLATFORMS = ('linux', 'windows', 'macos', 'iphone', 'ipad', 'android')
PRODUCT_CATALOG = 'EXReaderProductCatalog'
SQLITE_ENTRY = 'sqlite3_open_v2'
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
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def safe_name(name):
    parts = name.split('/')
    require(name and not PurePosixPath(name).is_absolute() and '\\' not in name and ':' not in name
            and all(p not in ('', '.', '..') for p in parts), 'unsafe path: ' + name)
    return parts


def identity(platform=None, sdk_version=None):
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'], base_sha=BASE, platform=platform,
                sdk_version=sdk_version)


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


def bind_results(results):
    """Aggregate per-platform audit results; never mixes sources and never grants acceptance.

    `results` maps platform -> dict(source_sha, run_id, attempt, sdk_version, passed, ...).
    Returns the aggregate record. Acceptance flags are always False here: a six-platform
    claim needs the manager's independent review of retained raw artifacts, not this gate.
    """
    require(set(results) <= set(PLATFORMS), 'unknown platform in results')
    sources = {r['source_sha'] for r in results.values()}
    runs = {(r['run_id'], r['attempt']) for r in results.values()}
    mixed = len(sources) > 1 or len(runs) > 1
    missing = [p for p in PLATFORMS if p not in results]
    failed = [p for p, r in results.items() if r.get('passed') is not True]
    record = dict(platforms=sorted(results), missing=missing, failed=failed, mixed_source_or_run=mixed,
                  same_source_complete=bool(results) and not missing and not failed and not mixed)
    for flag in ACCEPT_FLAGS:
        record[flag] = False
    return record

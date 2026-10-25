#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pure helpers shared by the S02 Linux relocatable-candidate verification.

Nothing in this module touches the network or the GUI: it parses tool output,
walks trees, seals nothing (sealing is reused from the reviewed J24 tool) and
provides the small assertion vocabulary every S02 step reports through.
"""
import hashlib
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

# Producer build tokens that must never survive inside a redistributable tree.
BUILD_TOKENS = ('EXReader/EXReader/build', 'compact-desktop', 'reading-library/stage',
                'account-stage', 'build/gtk-')
# Recorded only: a release build may legitimately embed the source path, never a
# build directory.
RECORD_TOKENS = ('/home/runner/work',)

KEEP_ENV = ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'LANG', 'LC_ALL',
            'XDG_RUNTIME_DIR', 'TMPDIR')


class S02Error(RuntimeError):
    """A verification invariant failed; the message names it."""


def need(value, message):
    if not value:
        raise S02Error(message)
    return value


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(str(path), 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    return path


def git(*arguments, cwd=None):
    rendered = [str(item) for item in arguments]
    result = subprocess.run(['git', *rendered], cwd=None if cwd is None else str(cwd),
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise S02Error('git %s failed: %s' % (' '.join(rendered), result.stderr.strip()))
    return result.stdout.strip()


def run(*arguments, cwd=None, env=None, check=True, timeout=900):
    process = subprocess.run([str(item) for item in arguments], cwd=None if cwd is None else str(cwd),
                             env=env, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=timeout)
    if check and process.returncode != 0:
        raise S02Error('command failed (%d): %s\nstdout:\n%s\nstderr:\n%s' % (
            process.returncode, ' '.join(str(item) for item in arguments),
            process.stdout[-4000:], process.stderr[-4000:]))
    return process


def walk_tree(root):
    """Record every regular file with bytes, digest and mode; symlinks are refused."""
    root = Path(root)
    need(root.is_dir(), 'missing tree: %s' % root)
    records = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        need(not path.is_symlink(), 'symlink in tree: %s' % relative)
        if path.is_dir():
            continue
        status = path.stat()
        records.append({'path': relative, 'bytes': status.st_size,
                        'sha256': sha256_file(path),
                        'executable': bool(status.st_mode & 0o111),
                        'mode': status.st_mode & 0o777})
    need(records, 'empty tree: %s' % root)
    return records


def tree_problems(root, records):
    root = Path(root)
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*')
              if path.is_file() and not path.is_symlink()}
    claimed = {record['path'] for record in records}
    problems = []
    if actual != claimed:
        problems.append('tree inventory differs: missing=%s unlisted=%s' % (
            sorted(claimed - actual)[:8], sorted(actual - claimed)[:8]))
    for record in records:
        path = root / record['path']
        if not path.is_file() or path.is_symlink():
            problems.append('missing file: ' + record['path'])
            continue
        if path.stat().st_size != record['bytes'] or sha256_file(path) != record['sha256']:
            problems.append('file changed: ' + record['path'])
    return problems


def safe_extract_tar(archive, destination, expect_root=None):
    """Extract a single-root tarball, refusing links and escaping members.

    shutil.make_archive(root_dir=payload) stores the payload *contents* behind a
    '.' member, while a hand-built archive may keep a named root directory; both
    layouts are accepted and the effective root is reported.
    """
    destination = Path(destination)
    need(not destination.exists(), 'tar destination already exists: %s' % destination)
    destination.mkdir(parents=True)
    entries, roots = [], set()
    with tarfile.open(str(archive), 'r:gz') as tar:
        for member in tar.getmembers():
            name = member.name
            need(name and not name.startswith('/'), 'absolute tar member: %s' % name)
            parts = [part for part in name.split('/') if part not in ('', '.')]
            need('..' not in parts, 'escaping tar member: %s' % name)
            need(not member.issym() and not member.islnk(),
                 'tar links are refused: %s' % name)
            if not parts:
                need(member.isdir(), 'archive root member is not a directory: %s' % name)
                roots.add('.')
                continue
            need(member.isdir() or member.isfile(), 'unexpected tar member: %s' % name)
            roots.add(parts[0])
            if member.isdir():
                continue
            entries.append((parts, member))
    need(roots, 'empty tar archive: %s' % archive)
    named = {root for root in roots if root != '.'}
    need(len(named) <= 1, 'tar has several roots: %s' % sorted(roots))
    root = named.pop() if named else '.'
    need(expect_root is None or root in (expect_root, '.'),
         'tar root %r differs from %r' % (root, expect_root))
    members = []
    for parts, member in entries:
        relative = parts[1:] if (root != '.' and parts[0] == root) else parts
        need(relative, 'tar member outside its root: %s' % member.name)
        target = destination.joinpath(*relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = tar.extractfile(member)
        need(source is not None, 'unreadable tar member: %s' % member.name)
        with source:
            target.write_bytes(source.read())
        os.chmod(str(target), member.mode & 0o777)
        members.append({'path': '/'.join(relative), 'bytes': target.stat().st_size,
                        'sha256': sha256_file(target), 'mode': member.mode & 0o777})
    return {'root': root, 'members': members}


def parse_readelf(text):
    """Parse readelf -dW output into NEEDED/RPATH/RUNPATH/SONAME."""
    needed, rpath, runpath, soname = [], [], [], None
    for line in text.splitlines():
        match = re.search(r'\((NEEDED|RPATH|RUNPATH|SONAME)\)\s+[^:]+:\s*\[([^\]]*)\]', line)
        if not match:
            continue
        kind, value = match.group(1), match.group(2)
        if kind == 'NEEDED':
            needed.append(value)
        elif kind == 'RPATH':
            rpath.extend(item for item in value.split(':') if item)
        elif kind == 'RUNPATH':
            runpath.extend(item for item in value.split(':') if item)
        else:
            soname = value
    return {'needed': needed, 'rpath': rpath, 'runpath': runpath, 'soname': soname}


def parse_ldd(text):
    items, not_found, unparsed, virtual = [], [], [], []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^(\S+)\s+=>\s+(\S+)\s+\(0x[0-9a-fA-F]+\)$', line)
        if match:
            items.append({'name': match.group(1), 'path': match.group(2)})
            continue
        match = re.match(r'^(\S+)\s+=>\s+not found$', line)
        if match:
            not_found.append(match.group(1))
            continue
        match = re.match(r'^(\S+)\s+\(0x[0-9a-fA-F]+\)$', line)
        if match:
            token = match.group(1)
            if token.startswith('linux-vdso') or token.startswith('linux-gate'):
                virtual.append(token)
            else:
                items.append({'name': token, 'path': token})
            continue
        unparsed.append(line)
    return {'items': items, 'not_found': not_found, 'unparsed': unparsed,
            'virtual': virtual}


def classify_path(path, prefixes):
    """Classify a resolved path against named prefixes, then against system roots."""
    resolved = os.path.realpath(str(path))
    for label in sorted(prefixes):
        prefix = prefixes[label]
        if not prefix:
            continue
        prefix = os.path.realpath(str(prefix))
        if resolved == prefix or resolved.startswith(prefix.rstrip('/') + '/'):
            return label
    if resolved.startswith(('/usr/', '/lib', '/opt/')) and not resolved.startswith('/opt/hostedtoolcache'):
        return 'system'
    return 'other'


def desktop_exec(path):
    value = str(path)
    need(os.path.isabs(value), 'desktop Exec must be absolute: %s' % value)
    need('"' not in value and '\n' not in value, 'desktop Exec cannot be quoted: %s' % value)
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    escaped = escaped.replace('$', '\\$').replace('`', '\\`')
    if re.search(r'[\s"\'\\><~|&;$*?#()]', value):
        return '"' + escaped + '"'
    return escaped


DESKTOP_ENTRY = """[Desktop Entry]
Type=Application
Version=1.0
Name=EXReader
GenericName=Reader
Comment=EXReader native reading application
Exec={exec}
Terminal=false
Categories=Office;Viewer;
StartupNotify=true
StartupWMClass=EXReader Linux
"""


def render_desktop_entry(exec_path):
    return DESKTOP_ENTRY.format(exec=desktop_exec(exec_path))


def parse_observation(text):
    values = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('[') or '=' not in stripped:
            continue
        key, value = stripped.split('=', 1)
        values[key.strip()] = value.strip()
    return values


def observation_int(values, key, default=None):
    if key not in values:
        return default
    try:
        return int(values[key])
    except (TypeError, ValueError):
        return default


def scan_tokens(root, tokens, limit=512 * 1024 * 1024):
    hits, skipped = [], []
    encoded = [(token, token.encode('utf-8')) for token in tokens if token]
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        size = path.stat().st_size
        if size > limit:
            skipped.append({'path': path.relative_to(Path(root)).as_posix(), 'bytes': size})
            continue
        data = path.read_bytes()
        for token, needle in encoded:
            count = data.count(needle)
            if count:
                hits.append({'path': path.relative_to(Path(root)).as_posix(),
                             'token': token, 'count': count})
    return {'hits': hits, 'skipped': skipped}


def minimal_env(overrides):
    """Environment for the packaged application: no HOME state, no library path."""
    env = {name: os.environ[name] for name in KEEP_ENV if name in os.environ}
    env.setdefault('PATH', '/usr/local/bin:/usr/bin:/bin')
    for name in ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'PYTHONPATH', 'PYTHONHOME',
                 'GTK_PATH', 'GTK_MODULES'):
        env.pop(name, None)
    env.update({name: str(value) for name, value in overrides.items()})
    return env


def library_loads(log_text):
    found = []
    for line in log_text.splitlines():
        marker = 'calling init: '
        if marker in line:
            value = line.split(marker, 1)[1].strip()
            if value:
                found.append(value)
    return found


class Checks:
    """Ordered, named check records; acceptance requires every check to pass."""

    def __init__(self, stream=True):
        self.items = []
        self.stream = stream

    def add(self, identifier, ok, detail, **extra):
        row = {'id': identifier, 'status': 'pass' if ok else 'fail', 'detail': detail}
        row.update(extra)
        self.items.append(row)
        if self.stream:
            print(json.dumps({'check': identifier, 'status': row['status'],
                              'detail': detail}, ensure_ascii=False), flush=True)
        return bool(ok)

    def failed(self):
        return [row['id'] for row in self.items if row['status'] != 'pass']

    def accepted(self):
        return bool(self.items) and not self.failed()

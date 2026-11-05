"""Shared read-only helpers for the C08 public-SDK readback package.

Every helper here is Actions-only: it downloads and inspects the authenticated
producer artifact, never the local checkout build outputs.
"""
import hashlib
import io
import json
import os
import pathlib
import subprocess
import zipfile

MAX_ARTIFACT_ENTRIES = 80000
MAX_ARTIFACT_BYTES = 6 * 1024 ** 3


def require_actions():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('C08 tooling only runs inside GitHub Actions')


def identity():
    return {'source_sha': os.environ['GITHUB_SHA'],
            'run_id': os.environ['GITHUB_RUN_ID'],
            'attempt': os.environ['GITHUB_RUN_ATTEMPT']}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))


def repo_slug():
    return os.environ['GITHUB_REPOSITORY']


def gh_api(path, timeout=180):
    body = subprocess.check_output(
        ['gh', 'api', 'repos/' + repo_slug() + '/' + path], timeout=timeout)
    return json.loads(body)


def gh_api_bytes(path, timeout=1200):
    return subprocess.check_output(
        ['gh', 'api', 'repos/' + repo_slug() + '/' + path], timeout=timeout)


def safe_extract(body, destination):
    """Extract an artifact ZIP after rejecting anything that could escape."""
    destination = pathlib.Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    (pathlib.Path(destination) / 'artifact.zip').write_bytes(body)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise SystemExit('artifact ZIP has duplicate entries')
        if len(names) > MAX_ARTIFACT_ENTRIES:
            raise SystemExit('artifact ZIP has too many entries')
        total = 0
        for name in names:
            path = pathlib.PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                raise SystemExit('unsafe artifact entry: ' + name)
            info = archive.getinfo(name)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise SystemExit('artifact entry is a symlink: ' + name)
            total += info.file_size
            if total > MAX_ARTIFACT_BYTES:
                raise SystemExit('artifact ZIP expands beyond its byte ceiling')
        archive.extractall(destination)
    return destination


def find_suffix(root, suffix):
    root = pathlib.Path(root)
    wanted = suffix.replace('\\', '/').lstrip('/')
    found = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if wanted.startswith('.'):
            if relative.endswith(wanted):
                found.append(path)
        elif relative == wanted or relative.endswith('/' + wanted):
            found.append(path)
    return sorted(found)


def run(command, cwd=None, timeout=600, check=True, input=None, binary=False):
    process = subprocess.run(command, cwd=cwd, timeout=timeout, input=input,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if check and process.returncode != 0:
        text = process.stdout if binary else process.stdout.decode('utf-8', 'replace')
        raise SystemExit('command failed (%d): %s\n%s' % (process.returncode, ' '.join(command), text[-4000:]))
    return process.stdout if binary else process.stdout.decode('utf-8', 'replace')

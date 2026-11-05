#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage an app bundle out of an authenticated artifact ZIP.

The ZIP bytes are authenticated by the caller before this module runs. ditto is
used on macOS so the extracted bundle keeps its modes and symlinks; the pure
zipfile path restores the recorded Unix mode and refuses unsafe names.
"""
import hashlib
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import subprocess
import sys
import zipfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def extract(archive, destination):
    archive = Path(archive)
    destination = Path(destination)
    require(archive.is_file(), 'missing artifact archive: ' + str(archive))
    with open(archive, 'rb') as stream:
        require(stream.read(4) == b'PK\x03\x04', 'artifact is not a ZIP archive: ' + str(archive))
    destination.mkdir(parents=True)
    if sys.platform == 'darwin' and shutil.which('ditto'):
        subprocess.run(['ditto', '-x', '-k', str(archive), str(destination)], check=True,
                       capture_output=True)
        return 'ditto'
    with zipfile.ZipFile(str(archive)) as bundle:
        for entry in bundle.infolist():
            name = entry.filename
            parts = PurePosixPath(name).parts
            require(not name.startswith('/') and '..' not in parts, 'unsafe ZIP entry: ' + name)
            target = destination.joinpath(*parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(entry) as source, open(target, 'wb') as stream:
                shutil.copyfileobj(source, stream)
            mode = (entry.external_attr >> 16) & 0xFFFF
            if mode:
                os.chmod(target, mode)
    return 'zipfile'


def find_apps(root):
    root = Path(root)
    apps = []
    for path in sorted(root.rglob('*.app')):
        if not path.is_dir():
            continue
        nested = False
        for parent in path.parents:
            if parent == root:
                break
            if parent.suffix == '.app':
                nested = True
                break
        if not nested:
            apps.append(path)
    return apps


def app_facts(app):
    app = Path(app)
    info_path = app / 'Info.plist'
    info = {}
    error = None
    if info_path.is_file():
        try:
            info = plistlib.loads(info_path.read_bytes())
        except Exception as failure:
            error = str(failure)
    executable = info.get('CFBundleExecutable')
    executable_path = app / executable if executable else None
    files = []
    for root, _dirnames, filenames in os.walk(str(app), followlinks=False):
        for name in filenames:
            path = Path(root) / name
            if path.is_symlink() or not path.is_file():
                continue
            files.append(path)
    return {
        'path': app.as_posix(),
        'bytes': sum(path.stat().st_size for path in files),
        'files': len(files),
        'identifier': info.get('CFBundleIdentifier'),
        'executable': executable,
        'executable_bytes': executable_path.stat().st_size if executable_path and executable_path.is_file() else None,
        'executable_sha256': sha256(executable_path) if executable_path and executable_path.is_file() else None,
        'info_plist_sha256': sha256(info_path) if info_path.is_file() else None,
        'platform': info.get('CFBundleSupportedPlatforms'),
        'family': info.get('UIDeviceFamily'),
        'source_sha': info.get('EXRSourceSHA'),
        'sdk_version': info.get('EXRSDKVersion'),
        'minimum_os': info.get('MinimumOSVersion'),
        'fixture': bool(info.get('S05Fixture')),
        'info_error': error,
    }

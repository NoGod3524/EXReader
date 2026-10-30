"""Strict ZIP reading shared by the handoff checks; never uses ZipFile.extractall."""
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath


class UnsafeArchive(Exception):
    pass


def validate(infos, label):
    seen, folded = set(), set()
    for info in infos:
        name = info.filename
        if not name or '\x00' in name or '\\' in name or name.startswith('/') or re.match(r'^[A-Za-z]:', name):
            raise UnsafeArchive(label + ': unsafe member name ' + repr(name))
        if any(part == '..' for part in name.split('/')):
            raise UnsafeArchive(label + ': parent traversal in ' + repr(name))
        if name in seen or name.lower() in folded:
            raise UnsafeArchive(label + ': duplicate member ' + repr(name))
        seen.add(name)
        folded.add(name.lower())
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK or (mode and mode not in (stat.S_IFREG, stat.S_IFDIR)):
            raise UnsafeArchive(label + ': non-regular member ' + repr(name))
        if info.flag_bits & 0x1:
            raise UnsafeArchive(label + ': encrypted member ' + repr(name))


def read_members(path, label=None):
    """Return {name: bytes} for regular files after validating every member name."""
    label = label or str(path)
    with zipfile.ZipFile(path) as bundle:
        infos = bundle.infolist()
        validate(infos, label)
        return {info.filename: bundle.read(info) for info in infos if not info.is_dir()}


def extract(path, destination, label=None):
    """Write validated regular files below an empty destination; returns the member map."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    members = read_members(path, label)
    for name, data in members.items():
        target = (root / PurePosixPath(name)).resolve()
        if root not in target.parents:
            raise UnsafeArchive((label or str(path)) + ': member escapes destination ' + repr(name))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return members

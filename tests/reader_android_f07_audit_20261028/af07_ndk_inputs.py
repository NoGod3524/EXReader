"""Strict link-time script resolution, separate from dynamic OS providers."""
from pathlib import Path
import re

import af07_contract as C


def input_tokens(payload):
    C.require(len(payload) <= 4096, 'linker script exceeds supported budget')
    text = payload.decode('ascii')
    match = re.fullmatch(r'INPUT\(\s*((?:-l[A-Za-z0-9_+.\-]+\s*)+)\)', text)
    C.require(match is not None, 'unsupported linker script directive/input')
    tokens = match[1].split()
    C.require(all(re.fullmatch(r'-l[A-Za-z0-9_+][A-Za-z0-9_+.\-]*', token) for token in tokens),
              'unsafe linker script library token')
    return tokens


def resolve(path, sysroot, search, chain=()):
    """Only INPUT(-lname...) in exact API/triple search directories is supported.

    This is link-input attribution, never a runtime provider grant. Unsupported
    directives, absolute paths, escapes, symlinks, cycles and missing targets
    fail; no shell, linker or captured payload is invoked.
    """
    path, sysroot = Path(path), Path(sysroot).resolve()
    search = tuple(Path(directory) for directory in search)
    C.require(all(directory.is_dir() and directory.resolve().is_relative_to(sysroot) and
                  directory.absolute() == directory.resolve() for directory in search),
              'noncanonical/escaping linker search directory')
    C.require(path.is_file() and not path.is_symlink() and path.absolute() == path.resolve() and
              path.resolve().is_relative_to(sysroot), 'noncanonical/escaping linker input')
    name = path.relative_to(sysroot).as_posix()
    C.require(name not in chain, 'cyclic linker script input')
    with path.open('rb') as stream: magic = stream.read(8)
    record = dict(path=name, bytes=path.stat().st_size, sha256=C.digest(path))
    if magic.startswith(b'\x7fELF'):
        return dict(record, kind='ELF', children=[])
    if magic == b'!<arch>\n':
        return dict(record, kind='archive', children=[])
    C.require(path.stat().st_size <= 4096, 'nonobject input exceeds script budget')
    payload = path.read_bytes(); tokens = input_tokens(payload)
    children = []
    for token in tokens:
        library = token[2:]
        candidates = [directory / ('lib' + library + suffix)
                      for directory in search for suffix in ('.so', '.a')]
        existing = [candidate for candidate in candidates if candidate.exists() or candidate.is_symlink()]
        C.require(existing, 'linker script library not found in exact selected search path')
        children.append(resolve(existing[0], sysroot, search, chain + (name,)))
    return dict(record, kind='INPUT-script', text=payload.decode('ascii'), tokens=tokens, children=children)


def system_names(metadata, api):
    C.require(isinstance(metadata, dict) and metadata, 'missing NDK system library manifest')
    C.require(all(re.fullmatch(r'lib[A-Za-z0-9_+.-]+\.so', name) and
                  ((type(level) is int and level > 0) or
                   (type(level) is str and re.fullmatch(r'[1-9][0-9]*', level)))
                  for name, level in metadata.items()), 'unsupported NDK system library metadata')
    return {name for name, level in metadata.items() if int(level) <= api}

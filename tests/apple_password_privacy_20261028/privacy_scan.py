# SPDX-License-Identifier: MIT
"""Streaming privacy oracle for quiescent, private product files (no size skip)."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import quote_from_bytes

CHUNK = 1024 * 1024


def require(value, message):
    if not value:
        raise RuntimeError(message)


def needles(values):
    result = {}
    for label, raw in values.items():
        require(isinstance(raw, bytes) and len(raw) >= 16, 'synthetic canary too short')
        forms = {'raw': raw, 'hex': raw.hex().encode(), 'HEX': raw.hex().upper().encode(),
                 'base64': base64.b64encode(raw), 'base64url': base64.urlsafe_b64encode(raw),
                 'url': quote_from_bytes(raw, safe='').encode()}
        forms['base64-no-padding'] = forms['base64'].rstrip(b'=')
        forms['base64url-no-padding'] = forms['base64url'].rstrip(b'=')
        forms['url-lower-escape'] = re.sub(rb'%[0-9A-F]{2}', lambda match: match.group().lower(), forms['url'])
        forms['url-all'] = ''.join('%%%02X' % value for value in raw).encode()
        forms['url-all-lower'] = forms['url-all'].lower()
        try:
            text = raw.decode('utf-8')
            forms.update({'utf16le': text.encode('utf-16le'), 'utf16be': text.encode('utf-16be'),
                          'utf32le': text.encode('utf-32le'), 'utf32be': text.encode('utf-32be'),
                          'json': json.dumps(text, ensure_ascii=True)[1:-1].encode(),
                          'json-unicode': ''.join('\\u%04x' % ord(value) for value in text).encode()})
        except UnicodeDecodeError:
            pass
        for form, value in forms.items():
            result[label + ':' + form] = value
    require(bool(result), 'no canary variants')
    return result


def identity(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def regular(value):
    # Windows junctions/reparse points and POSIX symlinks are not followed.
    return stat.S_ISREG(value.st_mode) and not (getattr(value, 'st_file_attributes', 0) & 0x400)


def scan_file(path, variants, chunk_size=CHUNK):
    require(type(chunk_size) is int and chunk_size > 0, 'invalid chunk size')
    initial = path.lstat()
    require(regular(initial), 'scan input is not a regular owned file')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        require(regular(opened) and identity(opened) == identity(initial), 'file replaced before privacy read')
        maximum = max(map(len, variants.values())) - 1
        overlap, total, chunks, hits, checksum = b'', 0, 0, set(), hashlib.sha256()
        while True:
            data = os.read(descriptor, chunk_size)
            if not data:
                break
            checksum.update(data); total += len(data); chunks += 1
            combined = overlap + data
            hits.update(label for label, value in variants.items() if value in combined)
            overlap = combined[-maximum:] if maximum else b''
        require(identity(os.fstat(descriptor)) == identity(initial) and identity(path.lstat()) == identity(initial),
                'file changed during privacy read')
        require(total == initial.st_size, 'privacy scan short read')
        return {'bytes': total, 'chunks': chunks, 'sha256': checksum.hexdigest(), 'hits': sorted(hits)}
    finally:
        os.close(descriptor)


def scan_tree(root, variants, chunk_size=CHUNK, allow_empty=False):
    root = Path(root)
    start = root.lstat()
    require(stat.S_ISDIR(start.st_mode) and not (getattr(start, 'st_file_attributes', 0) & 0x400), 'invalid scan root')
    files, total, visited, inspected, paths = [], 0, {}, {}, []
    def fail_walk(error): raise error
    for folder, directories, names in os.walk(root, followlinks=False, onerror=fail_walk):
        visited[Path(folder)] = identity(Path(folder).lstat())
        directories.sort()
        for name in sorted(directories):
            path = Path(folder) / name
            value = path.lstat()
            require(stat.S_ISDIR(value.st_mode) and not (getattr(value, 'st_file_attributes', 0) & 0x400),
                    'linked or special directory in private scan')
            relative = path.relative_to(root).as_posix()
            hits = sorted(label for label, value in variants.items() if value in relative.encode('utf-8'))
            paths.append({'path': '<canary-in-path>' if hits else relative, 'path_hits': hits})
        for name in sorted(names):
            path = Path(folder) / name
            inspected[path] = identity(path.lstat())
            record = scan_file(path, variants, chunk_size)
            require(identity(path.lstat()) == inspected[path], 'file changed around privacy read')
            relative = path.relative_to(root).as_posix()
            path_hits = [label for label, value in variants.items() if value in relative.encode('utf-8')]
            record['path'] = '<canary-in-path>' if path_hits else relative
            record['path_hits'] = sorted(path_hits)
            files.append(record); total += record['bytes']
    require(all(identity(path.lstat()) == value for path, value in visited.items()), 'scan directory changed')
    require(all(identity(path.lstat()) == value for path, value in inspected.items()), 'earlier file changed before tree scan completed')
    require(identity(root.lstat()) == identity(start), 'scan root changed')
    require(bool(files) or allow_empty is True, 'empty scan does not prove product privacy')
    return {'accepted': all(not file['hits'] and not file['path_hits'] for file in files) and all(not item['path_hits'] for item in paths),
            'bytes': total, 'file_count': len(files), 'files': files,
            'directories': paths,
            'chunk_bytes': chunk_size, 'variant_labels': sorted(variants), 'size_skips': 0,
            'symlinks_followed': False, 'unreadable_files_ignored': False, 'empty_root_allowed': allow_empty}


def inventory(root):
    """Identity of every entry, including already-scanned directory prefixes."""
    root = Path(root)
    result = {'.': identity(root.lstat())}
    require(stat.S_ISDIR(root.lstat().st_mode), 'invalid inventory root')
    def fail_walk(error): raise error
    for folder, directories, names in os.walk(root, followlinks=False, onerror=fail_walk):
        for name in sorted(directories + names):
            path = Path(folder) / name
            value = path.lstat()
            require((regular(value) or stat.S_ISDIR(value.st_mode)) and
                    not (getattr(value, 'st_file_attributes', 0) & 0x400), 'linked or special scan entry')
            result[path.relative_to(root).as_posix()] = identity(value)
    return result


def scan_roots(roots, variants, chunk_size=CHUNK):
    """Reject mutation of an earlier file/root while later roots are read."""
    before = {label: inventory(path) for label, path in sorted(roots.items())}
    scans = {label: scan_tree(path, variants, chunk_size, allow_empty=label in ('cache', 'saved-state'))
             for label, path in sorted(roots.items())}
    after = {label: inventory(path) for label, path in sorted(roots.items())}
    require(before == after, 'private roots changed during complete privacy scan')
    return scans


def optional_entries(paths):
    """Bind absent roots too; a dangling link is present and must refuse."""
    result = {}
    for label, path in sorted(paths.items()):
        try: value = path.lstat()
        except FileNotFoundError:
            result[label] = None; continue
        require((regular(value) or stat.S_ISDIR(value.st_mode)) and
                not (getattr(value, 'st_file_attributes', 0) & 0x400), 'linked or special optional private root')
        result[label] = identity(value)
    return result


def verify_optional_entries(paths, before):
    require(optional_entries(paths) == before, 'optional private root appeared, disappeared or changed')

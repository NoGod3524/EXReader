# SPDX-License-Identifier: MIT
"""Fail-closed Actions archive extraction; never merge aliased private members."""
from pathlib import PurePosixPath
import stat
import unicodedata
import zipfile
from contract import require

MAX_MEMBER_BYTES = 8 * 1024 ** 3
MAX_TOTAL_BYTES = 32 * 1024 ** 3


def safe_members(archive):
    members, names, prefixes, total = archive.infolist(), set(), {}, 0
    for item in members:
        name, path = item.filename, PurePosixPath(item.filename)
        require(name and path.parts and name not in names and item.orig_filename == name and not path.is_absolute() and
                '..' not in path.parts and '\\' not in name and ':' not in name and
                not any(ord(character) < 32 or ord(character) == 127 for character in name) and
                path.as_posix() + ('/' if item.is_dir() else '') == name, 'unsafe or duplicate ZIP entry')
        names.add(name)
        require(all(part and not part.endswith((' ', '.')) for part in path.parts), 'ambiguous ZIP component')
        kind = stat.S_IFMT(item.external_attr >> 16)
        require(kind in (0, stat.S_IFREG, stat.S_IFDIR) and
                (kind != stat.S_IFDIR or item.is_dir()) and (kind != stat.S_IFREG or not item.is_dir()), 'linked or special ZIP entry')
        require(not item.flag_bits & 1 and 0 <= item.file_size <= MAX_MEMBER_BYTES and item.compress_size >= 0 and
                (not item.is_dir() or item.file_size == 0), 'unsupported or oversized ZIP member')
        total += item.file_size
        require(total <= MAX_TOTAL_BYTES, 'oversized ZIP total')
        for index in range(1, len(path.parts) + 1):
            parts = path.parts[:index]
            spelling = '/'.join(parts)
            canonical = '/'.join(unicodedata.normalize('NFC', unicodedata.normalize('NFC', part).casefold()) for part in parts)
            directory = index < len(path.parts) or item.is_dir()
            record = (spelling, directory)
            require(canonical not in prefixes or prefixes[canonical] == record, 'ZIP case/Unicode alias or file-directory collision')
            prefixes[canonical] = record
    return members


def safe_extract(path, destination):
    with zipfile.ZipFile(path) as archive:
        # Validate the whole namespace before writing the first extracted byte.
        safe_members(archive)
        archive.extractall(destination)

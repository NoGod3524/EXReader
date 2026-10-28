"""Additive Android F07 evidence capture; execution is restricted to Actions."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '8f8acf3234cba747165f001c0c96efe1b911e6ad'
BRANCH = 'codex/android-f07-capture-20261028'
OUT = ROOT / 'build/android-f07-capture'
OWNED = (
    'tests/reader_android_f07_capture_20261028/contract.py',
    'tests/reader_android_f07_capture_20261028/run.py',
    'tests/reader_android_f07_capture_20261028/test_contract.py',
    '.github/workflows/android-f07-capture-20261028.yml',
    'docs/reader-total-progress/android-f07-capture-20261028.md',
)


def require(value, message):
    if not value:
        raise ValueError(message)


def actions_only():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actions execution only')
    require(os.environ.get('GITHUB_REPOSITORY') == 'NoGod3524/EXReader', 'wrong repository')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def identity():
    return dict(source_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                attempt=os.environ['GITHUB_RUN_ATTEMPT'], common_base=BASE)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def guard():
    actions_only()
    require(os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH, 'dedicated branch required')
    require(git('rev-parse', 'HEAD') == os.environ['GITHUB_SHA'], 'wrong checkout SHA')
    git('merge-base', '--is-ancestor', BASE, 'HEAD')
    lines = git('diff', '--name-status', '--no-renames', BASE, 'HEAD').splitlines()
    require(lines, 'no capture package changes')
    for line in lines:
        require(line.startswith('A\t') and line[2:] in OWNED, 'non-additive/out-of-scope change: ' + line)
    require({line[2:] for line in lines} == set(OWNED), 'exact five-file capture package required')
    require(not git('status', '--porcelain', '--untracked-files=no'), 'dirty tracked source before build')
    # The original producer guard deliberately rejects every new package path.
    # Replace only that branch allowlist with this stricter five-added-file scope;
    # never patch its builder, version adaptations, assertions or the F06 entry.
    frozen = {}
    for path in ('src', 'include', 'cmake', 'CMakeLists.txt', 'bindings', 'apps', 'examples',
                 'tests/android_sdk342_package', 'tests/reader_f06_packages',
                 'tests/reader_wave3_c11', 'tools/reader_wave3_package',
                 '.github/workflows/android-sdk342-package.yml',
                 '.github/workflows/android-composition-candidate.yml'):
        frozen[path] = git('rev-parse', 'HEAD:' + path)
        require(frozen[path] == git('rev-parse', BASE + ':' + path), 'frozen source changed: ' + path)
    git('diff', '--exit-code', '8357eafa28423a7ab93ba08b823af80f01ad1505', 'HEAD', '--',
        'src', 'include', 'cmake', 'CMakeLists.txt', 'bindings')
    report = dict(identity(), changed=lines, frozen=frozen, scope_guard_passed=True,
                  original_producer='tests/android_sdk342_package/run.py')
    (ROOT / 'build/f06').mkdir(parents=True, exist_ok=True)
    save(OUT / 'source.json', report)
    return report


def elf_allocated(data):
    """Bind stripped APK ELF to its exact link output via all allocated sections.

    This is explicitly NOT whole-file equality and not a provider/private-API
    verdict. Android Gradle stripping can remove nonallocated debug/symbol data.
    Reject unsupported/extended ELF tables rather than guessing.
    """
    require(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01', 'ELF64 little endian required')
    header = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    kind, machine, version, entry, phoff, shoff, flags, ehsize, phentsize, phnum, shentsize, shnum, shstrndx = header
    require(kind == 3 and machine == 62 and version == 1 and ehsize == 64, 'x86_64 shared ELF required')
    require(shentsize == 64 and 0 < shnum < 65535 and 0 < shstrndx < shnum, 'unsupported ELF section table')
    require(shoff + shnum * shentsize <= len(data), 'truncated ELF sections')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * shentsize) for i in range(shnum)]
    strings = sections[shstrndx]
    require(strings[4] + strings[5] <= len(data), 'truncated ELF names')
    names = data[strings[4]:strings[4] + strings[5]]
    rows, seen = [], set()
    for section in sections:
        nameoff, type_, attrs, address, offset, size, link, info, alignment, entsize = section
        if not attrs & 2:  # SHF_ALLOC only; SHT_NOBITS carries no file payload.
            continue
        require(nameoff < len(names) and b'\0' in names[nameoff:], 'bad ELF section name')
        name = names[nameoff:names.index(b'\0', nameoff)].decode('ascii')
        require(name and name not in seen, 'duplicate allocated section')
        seen.add(name)
        require(type_ == 8 or offset + size <= len(data), 'truncated allocated section')
        payload = b'' if type_ == 8 else data[offset:offset + size]
        rows.append(dict(name=name, type=type_, flags=attrs, address=address, size=size,
                         alignment=alignment, entsize=entsize, sha256=digest(payload)))
    require(rows and any(r['name'] == '.dynamic' for r in rows), 'no allocated dynamic section')
    # Program-header memory layout is retained too; file offsets/sizes can differ
    # only outside alloc sections and are not silently treated as byte identity.
    require(phentsize == 56 and 0 < phnum < 65535 and phoff + phnum * phentsize <= len(data), 'bad ELF program table')
    segments = []
    for i in range(phnum):
        p = struct.unpack_from('<IIQQQQQQ', data, phoff + i * phentsize)
        if p[0] == 1:  # PT_LOAD virtual layout, not section-table header bytes.
            segments.append(dict(flags=p[1], address=p[3], memory_size=p[6], alignment=p[7]))
    require(segments, 'no load segments')
    value = dict(machine=machine, type=kind, entry=entry, flags=flags,
                 allocated_sections=rows, load_segments=segments)
    value['allocated_sha256'] = digest(json.dumps(value, sort_keys=True).encode())
    return value

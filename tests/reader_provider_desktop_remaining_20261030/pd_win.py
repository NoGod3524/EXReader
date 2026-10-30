"""Windows readers: COFF archives/objects (pure Python), MSVC /MAP, dumpbin text. Read-only."""
import os
import re
import struct
import subprocess

BIGOBJ_CLASS = bytes.fromhex('C7A1BAD1EEBAA94BAF20FAF66AA4DCB8')
CLASS_EXTERNAL = 2
CLASS_WEAK_EXTERNAL = 105
SCN_LNK_COMDAT = 0x1000


def _fail(message):
    raise ValueError(message)


def empty_row():
    return dict(defined=set(), weak=set(), undefined=set())


def parse_coff_object(data):
    """-> ('object', row) | ('import', row) | ('other', None). COMDAT sections count as weak."""
    if len(data) < 20:
        _fail('truncated COFF member')
    sig1, sig2 = struct.unpack_from('<HH', data, 0)
    if sig1 == 0 and sig2 == 0xFFFF:
        if data[12:28] != BIGOBJ_CLASS:
            if len(data) >= 20 and struct.unpack_from('<H', data, 4)[0] == 0:
                return 'import', _import_row(data)
            return 'other', None
        nsec, symptr, nsyms = struct.unpack_from('<III', data, 44)
        sechdr, symsize, big = 56, 20, True
    else:
        _machine, nsec, _stamp, symptr, nsyms, opt, _chars = struct.unpack_from('<HHIIIHH', data, 0)
        sechdr, symsize, big = 20 + opt, 18, False
    chars = [struct.unpack_from('<I', data, sechdr + 40 * i + 36)[0] for i in range(nsec)]
    strtab = symptr + nsyms * symsize
    row = empty_row()
    i = 0
    while i < nsyms:
        off = symptr + i * symsize
        raw = data[off:off + 8]
        if big:
            value, section, _type, cls, aux = struct.unpack_from('<IiHBB', data, off + 8)
        else:
            value, section, _type, cls, aux = struct.unpack_from('<IhHBB', data, off + 8)
        if raw[:4] == b'\0\0\0\0':
            at = strtab + struct.unpack('<I', raw[4:])[0]
            name = data[at:data.index(b'\0', at)].decode('latin-1')
        else:
            name = raw.rstrip(b'\0').decode('latin-1')
        if cls == CLASS_EXTERNAL:
            if section == 0:
                (row['undefined'] if value == 0 else row['weak']).add(name)
            elif section > 0:
                if section - 1 >= len(chars):
                    _fail('symbol section out of range')
                (row['weak'] if chars[section - 1] & SCN_LNK_COMDAT else row['defined']).add(name)
        elif cls == CLASS_WEAK_EXTERNAL:
            row['weak'].add(name)
        i += 1 + aux
    return 'object', row


def _import_row(data):
    """Short import member: defines the symbol and its __imp_ thunk (data-only imports lack the thunk)."""
    parts = data[20:].split(b'\0')
    row = empty_row()
    if parts and parts[0]:
        name = parts[0].decode('latin-1')
        row['defined'].update((name, '__imp_' + name))
    return row


def parse_coff_archive(data):
    """-> (table {member basename: row}, kinds {member: object|import|other})."""
    if data[:8] != b'!<arch>\n':
        _fail('not a COFF archive')
    pos, longnames = 8, b''
    table, kind = {}, {}
    while pos + 60 <= len(data):
        header = data[pos:pos + 60]
        if header[58:60] != b'`\n':
            _fail('bad archive member header at %d' % pos)
        size = int(header[48:58].decode('ascii').strip())
        body = data[pos + 60:pos + 60 + size]
        pos += 60 + size + (size & 1)
        raw = header[:16]
        if raw.startswith(b'// '):
            longnames = body
            continue
        if raw.startswith(b'/ ') or raw.startswith(b'/<'):
            continue  # linker members, ARM64EC symbol members
        if raw[:1] == b'/' and raw[1:].strip().isdigit():
            at = int(raw[1:].strip())
            ends = [e for e in (longnames.find(b'\0', at), longnames.find(b'\n', at)) if e >= 0]
            name = longnames[at:min(ends) if ends else len(longnames)].decode('latin-1')
        else:
            name = raw.decode('latin-1').rstrip()
        if name.endswith('/'):
            name = name[:-1]
        key = member_key(name)
        what, row = parse_coff_object(body)
        kind[key] = what
        slot = table.setdefault(key, empty_row())
        if row:
            for field in slot:
                slot[field] |= row[field]
    return table, kind


def member_key(name):
    return name.replace('\\', '/').rsplit('/', 1)[-1].lower()


MAP_LINE = re.compile(r'^\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+(?P<sym>\S+)\s+(?P<rva>[0-9A-Fa-f]{8,16})\s+(?:[fi]\s+)*(?P<src>\S.*?)\s*$')
MEMBER = re.compile(r'^(?P<ar>.+?\.lib):(?P<mem>.+)$', re.I)


def parse_msvc_map(text):
    """Selected inputs from `Publics by Value` + `Static symbols`: archive members and loose objects."""
    if 'Publics by Value' not in text:
        _fail('not an MSVC link map')
    members, objects = set(), set()
    for line in text.split('Publics by Value', 1)[1].splitlines():
        m = MAP_LINE.match(line)
        if not m or m.group('src').startswith('<'):
            continue
        src = m.group('src')
        part = MEMBER.match(src)
        if part:
            members.add((part.group('ar'), member_key(part.group('mem'))))
        else:
            objects.add(src)
    if not members:
        _fail('MSVC map selects no library members')
    return dict(format='msvc', loads=[], members=sorted(members), objects=sorted(objects))


def resolve_input(path, link_cwd, lib_dirs):
    """Absolute normalised location of a map input: as given, link cwd, then the LIB search path."""
    text = path.replace('\\', '/')
    if re.match(r'^[A-Za-z]:/', text) or text.startswith('/'):
        return os.path.normpath(text).replace('\\', '/').lower()
    for base in [link_cwd, *lib_dirs]:
        candidate = os.path.normpath(os.path.join(base, text))
        if os.path.exists(candidate):
            return candidate.replace('\\', '/').lower()
    return os.path.normpath(os.path.join(link_cwd, text)).replace('\\', '/').lower()


def parse_dumpbin_dependents(text):
    start = text.find('Image has the following dependencies')
    if start < 0:
        return []
    end = text.find('Summary', start)
    return re.findall(r'^\s+(\S+\.dll)\s*$', text[start:end if end > 0 else None], re.M | re.I)


NOT_FUNCTIONS = {'Characteristics', 'Attributes'}


def parse_dumpbin_imports(text):
    """-> [dict(library, symbol, kind normal|delay)] from `dumpbin /imports`."""
    rows, mode, library = [], None, None
    for line in text.splitlines():
        if 'Section contains the following delay load imports' in line:
            mode, library = 'delay', None
            continue
        if 'Section contains the following imports' in line:
            mode, library = 'normal', None
            continue
        if mode is None or line.strip().startswith('Summary'):
            continue
        header = re.match(r'^\s{2,6}(\S+\.dll)\s*$', line, re.I)
        if header:
            library = header.group(1)
            continue
        if library is None:
            continue
        ordinal = re.match(r'^\s+Ordinal\s+(\d+)\s*$', line)
        if ordinal:
            rows.append(dict(library=library, symbol='#' + ordinal.group(1), kind=mode))
            continue
        func = re.match(r'^\s{8,}(?:[0-9A-Fa-f]+\s+)?(\S+)\s*$', line)
        if func and func.group(1) not in NOT_FUNCTIONS and not re.match(r'^[0-9A-Fa-f]+$', func.group(1)):
            rows.append(dict(library=library, symbol=func.group(1), kind=mode))
    return rows


def parse_dumpbin_exports(text):
    names = set()
    for line in text.splitlines():
        m = re.match(r'^\s+(\d+)\s+(?:[0-9A-Fa-f]+\s+)?(?:[0-9A-Fa-f]{8}\s+)?(\S+)(?:\s+=\s+\S+|\s+\(forwarded to .*\))?\s*$', line)
        if m:
            names.add(m.group(2))
    return names


def run_text(args):
    done = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        _fail('%s failed (%d): %s' % (args[0], done.returncode, done.stderr[:200]))
    return done.stdout.decode('utf-8', errors='replace')

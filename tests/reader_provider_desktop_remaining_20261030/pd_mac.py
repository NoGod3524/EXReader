"""macOS readers: `nm -m` Mach-O style, Apple ld map, otool -L, SDK .tbd stubs. Read-only."""
import os
import re
import subprocess


def _fail(message):
    raise ValueError(message)


def empty_row():
    return dict(defined=set(), weak=set(), undefined=set(), weakref=set())


WHERE = re.compile(r'\((?P<where>undefined|prebound undefined|absolute|common|indirect|[^()\s,][^(),]*,[^()]+)\)\s*(?P<rest>.*)$')
HEADERS = (re.compile(r'^(?P<ar>.+\.a)\((?P<mem>[^)]+)\):$'),
           re.compile(r'^(?P<ar>.+\.a):(?P<mem>[^:]+):$'),
           re.compile(r'^(?P<obj>.+):$'))


def parse_symbol_line(line):
    """One `nm -m` line -> dict(name, where, weak, private, source) or None for noise lines."""
    m = WHERE.search(line)
    if not m:
        return None
    rest = re.sub(r'\[[^\]]*\]', ' ', m.group('rest'))
    rest = re.sub(r'\(alignment[^)]*\)', ' ', rest)
    tokens = rest.split()
    if 'external' not in tokens and 'external)' not in tokens:
        return None
    k = tokens.index('external') if 'external' in tokens else tokens.index('external)')
    if k + 1 >= len(tokens):
        return None
    attrs = tokens[:k]
    source = re.search(r'\(from ([^)]+)\)', rest)
    return dict(name=tokens[k + 1], where=m.group('where'), weak='weak' in attrs, private='private' in attrs,
                source=source.group(1) if source else None, flat='dynamically looked up' in rest)


def add_symbol(row, sym):
    where = sym['where']
    if where in ('undefined', 'prebound undefined'):
        row['undefined'].add(sym['name'])
        if sym['weak']:
            row['weakref'].add(sym['name'])
    elif where in ('common',):
        row['weak'].add(sym['name'])
    elif where in ('absolute', 'indirect'):
        return
    else:
        (row['weak'] if sym['weak'] else row['defined']).add(sym['name'])


def parse_nm_members(text, single=None):
    """`nm -m -g` over one archive or one object -> {archive-or-object member: row}.

    Handles both `archive.a(member.o):` and `archive.a:member.o:` section headers; without a header
    every line belongs to `single`.
    """
    table, current = {}, single
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace() and not re.match(r'^[0-9a-fA-F]{8,16}\s', line) and line.endswith(':'):
            for pattern in HEADERS:
                h = pattern.match(line)
                if h:
                    current = h.groupdict().get('mem') or os.path.basename(h.group('obj'))
                    break
            table.setdefault(current, empty_row())
            continue
        sym = parse_symbol_line(line)
        if sym is None:
            continue
        if current is None:
            _fail('symbol line before any member header: ' + line[:100])
        add_symbol(table.setdefault(current, empty_row()), sym)
    return table


def parse_image_imports(text):
    """`nm -m -u image` -> [dict(symbol, weak, library, flat)]."""
    rows = []
    for line in text.splitlines():
        sym = parse_symbol_line(line)
        if sym and sym['where'] in ('undefined', 'prebound undefined'):
            rows.append(dict(symbol=sym['name'], weak=sym['weak'], library=sym['source'], flat=sym['flat']))
    return rows


def parse_apple_map(text):
    """Loaded inputs from `# Object files:`: archive members, loose objects, dylib/tbd inputs."""
    if '# Object files:' not in text or '# Symbols:' not in text:
        _fail('not an Apple ld map')
    head = text.split('# Object files:', 1)[1].split('# Sections:', 1)[0]
    members, objects, dylibs = set(), set(), set()
    for line in head.splitlines():
        m = re.match(r'^\[\s*\d+\]\s+(\S.*)$', line)
        if not m or m.group(1).strip() == 'linker synthesized':
            continue
        entry = m.group(1).strip()
        a = re.match(r'^(?P<ar>.+\.a)\((?P<mem>[^()]+)\)$', entry)
        if a:
            members.add((a.group('ar'), a.group('mem')))
        elif re.search(r'\.(?:dylib|tbd)$', entry) or '.framework/' in entry:
            dylibs.add(entry)
        else:
            objects.add(entry)
    if not members:
        _fail('Apple map selects no archive members')
    return dict(format='apple', loads=[], members=sorted(members), objects=sorted(objects), dylibs=sorted(dylibs))


def parse_otool_libraries(text):
    """`otool -L image` -> [install names] (first line is the image itself)."""
    names = []
    for line in text.splitlines()[1:]:
        m = re.match(r'^\s+(\S+) \(', line)
        if m:
            names.append(m.group(1))
    return names


def short_name(install_name):
    """The name `nm -m` prints after `from`: basename up to the first dot."""
    return os.path.basename(install_name).split('.')[0]


# ---- SDK text-based stubs ----------------------------------------------------------------------

def _block(document, key):
    m = re.search(r'^%s:[ \t]*\n(.*?)(?=^\S|\Z)' % re.escape(key), document, re.M | re.S)
    return m.group(1) if m else ''


def _list_items(text, key):
    items = []
    for m in re.finditer(r'\b%s:\s*\[(.*?)\]' % re.escape(key), text, re.S):
        items += [i.strip().strip('\'"') for i in m.group(1).split(',') if i.strip()]
    return items


def parse_tbd(text):
    """-> [dict(install_name, symbols, weak_symbols, reexports)] one entry per YAML document."""
    out = []
    for document in re.split(r'^--- .*$', text, flags=re.M):
        name = re.search(r'^install-name:\s*[\'"]?([^\'"\n]+)[\'"]?\s*$', document, re.M)
        if not name:
            continue
        exports = _block(document, 'exports')
        symbols = set(_list_items(exports, 'symbols')) | set(_list_items(exports, 'thread-local-symbols'))
        weak = set(_list_items(exports, 'weak-symbols'))
        for cls in _list_items(exports, 'objc-classes'):
            symbols.add('_OBJC_CLASS_$_' + cls)
            symbols.add('_OBJC_METACLASS_$_' + cls)
        for eh in _list_items(exports, 'objc-eh-types'):
            symbols.add('_OBJC_EHTYPE_$_' + eh)
        for iv in _list_items(exports, 'objc-ivars'):
            symbols.add('_OBJC_IVAR_$_' + iv)
        reexports = _list_items(_block(document, 'reexported-libraries'), 'libraries')
        out.append(dict(install_name=name.group(1).strip(), symbols=symbols, weak_symbols=weak, reexports=reexports))
    if not out:
        _fail('no tbd documents with install-name')
    return out


def tbd_path_for(install_name, sdk_root, extra_dirs=()):
    """SDK stub file for an install name, or None."""
    sdk_root = str(sdk_root)
    name = install_name
    candidates = []
    if name.startswith('@rpath/') or name.startswith('@'):
        base = os.path.basename(name)
        stem = re.sub(r'\.dylib$', '', base)
        for d in ('usr/lib/swift', 'usr/lib', 'usr/lib/system', *extra_dirs):
            candidates.append(os.path.join(sdk_root, d, stem + '.tbd'))
    else:
        path = name.lstrip('/')
        fw = re.match(r'^(.*\.framework)/(?:Versions/[^/]+/)?([^/]+)$', path)
        if fw:
            candidates.append(os.path.join(sdk_root, fw.group(1), fw.group(2) + '.tbd'))
        candidates.append(os.path.join(sdk_root, re.sub(r'\.dylib$', '.tbd', path)))
        stem = re.sub(r'\.dylib$', '', os.path.basename(path))
        if '.' in stem:  # libSystem.B.dylib -> libSystem.tbd style aliases
            candidates.append(os.path.join(sdk_root, os.path.dirname(path), stem.split('.')[0] + '.tbd'))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


class StubIndex:
    """Lazy, memoised symbol lookup through a library's stub and its re-export closure."""

    def __init__(self, sdk_root):
        self.sdk_root = sdk_root
        self.files = {}
        self.closures = {}

    def docs(self, path):
        if path not in self.files:
            with open(path, encoding='utf-8', errors='replace') as stream:
                self.files[path] = parse_tbd(stream.read())
        return self.files[path]

    def closure(self, install_name, limit=64):
        """Yield (stub path, document) for the library and everything it re-exports."""
        seen, queue, found = set(), [install_name], []
        while queue and len(seen) < limit:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            path = tbd_path_for(name, self.sdk_root)
            if not path:
                continue
            for document in self.docs(path):
                found.append((path, document))
                if document['install_name'] == name or name.startswith('@'):
                    queue.extend(document['reexports'])
                seen.add(document['install_name'])
        return found

    def provider(self, install_name, symbol):
        if install_name not in self.closures:
            self.closures[install_name] = self.closure(install_name)
        for path, document in self.closures[install_name]:
            if symbol in document['symbols'] or symbol in document['weak_symbols']:
                return dict(stub=os.path.relpath(path, self.sdk_root).replace(os.sep, '/'),
                            install_name=document['install_name'],
                            weak_definition=symbol in document['weak_symbols'])
        return None


def run_text(args):
    done = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if done.returncode:
        _fail('%s failed (%d): %s' % (args[0], done.returncode, done.stderr[:200]))
    return done.stdout.decode('utf-8', errors='replace')

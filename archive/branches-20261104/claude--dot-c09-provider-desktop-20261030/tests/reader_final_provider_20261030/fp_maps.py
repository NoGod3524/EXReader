"""Link-map parsers (GNU ld, lld ELF, Apple ld, MSVC link) and provider ownership policy.

Parsers fail closed on unrecognised syntax. They only read text; no build tool is run here.
"""
import re

SELECTING = ('T', 'D', 'B', 'R', 'S', 'C', 'V', 'W', 'G', 'I')
STRONG = ('T', 'D', 'B', 'R', 'S', 'G', 'I')


def _fail(message):
    raise ValueError(message)


def _split_member(text):
    """`dir/lib.a(member.o)` or `lib.lib:member.obj` -> (archive, member) or None for plain objects."""
    m = re.match(r'^(?P<ar>.+?\.(?:a|lib|framework))\((?P<mem>[^()]+)\)$', text)
    if m:
        return m.group('ar'), m.group('mem')
    m = re.match(r'^(?P<ar>.+?\.(?:a|lib)):(?P<mem>[^:\\/]+)$', text)
    if m:
        return m.group('ar'), m.group('mem')
    return None


def parse_gnu_map(text):
    loads = re.findall(r'^LOAD (.+)$', text, re.M)
    if not loads or 'Linker script and memory map' not in text:
        _fail('not a GNU ld map with LOAD records')
    members, objects = set(), set()
    for line in text.splitlines():
        m = re.match(r'^\s+\S+\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(\S.*)$', line)
        if not m or int(m.group(1), 16) == 0:
            continue
        member = _split_member(m.group(2).strip())
        (members.add(member) if member else objects.add(m.group(2).strip()))
    if not members:
        _fail('GNU map selects no archive members')
    return dict(format='gnu', loads=loads, members=sorted(members), objects=sorted(objects))


def parse_lld_map(text):
    if not re.search(r'^\s*VMA\s+LMA\s+Size\s+Align\s+Out\s+In\s+Symbol', text, re.M):
        _fail('not an lld ELF map')
    members, objects = set(), set()
    for line in text.splitlines():
        m = re.match(r'^\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)\s+\d+\s{2,}(\S+?):\([^)]*\)\s*$', line)
        if not m or int(m.group(1), 16) == 0:
            continue
        member = _split_member(m.group(2))
        (members.add(member) if member else objects.add(m.group(2)))
    if not members:
        _fail('lld map selects no archive members')
    return dict(format='lld', loads=[], members=sorted(members), objects=sorted(objects))


def parse_apple_map(text):
    if '# Object files:' not in text or '# Symbols:' not in text:
        _fail('not an Apple ld map')
    head = text.split('# Sections:')[0]
    members, objects = set(), set()
    for line in head.splitlines():
        m = re.match(r'^\[\s*\d+\]\s+(\S.*)$', line)
        if not m:
            continue
        member = _split_member(m.group(1).strip())
        (members.add(member) if member else objects.add(m.group(1).strip()))
    if not members:
        _fail('Apple map selects no archive members')
    return dict(format='apple', loads=sorted(objects), members=sorted(members), objects=sorted(objects))


def parse_msvc_map(text):
    if 'Publics by Value' not in text:
        _fail('not an MSVC link map')
    members, objects = set(), set()
    for line in text.split('Publics by Value', 1)[1].splitlines():
        m = re.match(r'^\s*[0-9a-f]{4}:[0-9a-f]+\s+\S+\s+[0-9a-f]+\s+(?:f\s+i?\s*|\s*)(\S+)\s*$', line)
        if not m:
            continue
        member = _split_member(m.group(1))
        (members.add(member) if member else objects.add(m.group(1)))
    if not members:
        _fail('MSVC map selects no library members')
    return dict(format='msvc', loads=[], members=sorted(members), objects=sorted(objects))


PARSERS = dict(gnu=parse_gnu_map, lld=parse_lld_map, apple=parse_apple_map, msvc=parse_msvc_map)

NM_LINE = re.compile(r'^(?P<ar>.+?\.(?:a|lib)):(?P<mem>[^:]+):\s*(?P<addr>[0-9a-fA-F]*)\s+(?P<kind>[A-Za-z?-])\s+(?P<sym>\S+)\s*$')


def parse_nm_archive(text):
    """`nm -A -g` over an archive -> {member: dict(defined=set, weak=set, undefined=set)}."""
    table = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        m = NM_LINE.match(line)
        if not m:
            _fail('unrecognised nm line: ' + line[:120])
        row = table.setdefault(m.group('mem'), dict(defined=set(), weak=set(), undefined=set()))
        kind = m.group('kind')
        if kind == 'U':
            row['undefined'].add(m.group('sym'))
        elif kind in ('w', 'W', 'v', 'V'):
            row['weak'].add(m.group('sym'))
        elif kind in STRONG:
            row['defined'].add(m.group('sym'))
        elif kind.islower() or kind in ('A', '?', '-'):
            continue
        else:
            _fail('unsupported nm kind ' + kind)
    return table


def classify(path, roles):
    """Longest-prefix role (sdk/product/host/system); the ProductCatalog archive name wins for product."""
    best, kind = -1, 'unknown'
    for role, prefixes in roles.items():
        for prefix in prefixes:
            if path.startswith(prefix) and len(prefix) > best:
                best, kind = len(prefix), role
    return kind


def audit(evidence, canon=lambda s: s):
    """Return a list of findings. Empty means this one platform's provider/map audit passed."""
    findings = []
    roles = evidence['roles']
    tables = {a: {m: {k: {canon(s) for s in v} for k, v in row.items()} for m, row in t.items()}
              for a, t in evidence['archives'].items()}
    selected = [tuple(x) for x in evidence['selected']]
    definers = {}
    for archive, member in selected:
        role = classify(archive, roles)
        if role == 'unknown':
            findings.append(dict(kind='unowned_link_input', archive=archive, member=member))
        if role == 'system':
            continue
        row = tables.get(archive, {}).get(member)
        if row is None:
            findings.append(dict(kind='selected_member_without_native_table', archive=archive, member=member))
            continue
        for symbol in row['defined']:
            definers.setdefault(symbol, []).append((archive, member))
    for symbol, owners in sorted(definers.items()):
        if len(set(owners)) > 1:
            findings.append(dict(kind='duplicate_provider', symbol=symbol, owners=sorted(set(owners))))
    entry = canon('sqlite3_open_v2')
    owners = definers.get(entry, [])
    if len(owners) != 1 or classify(owners[0][0], roles) != 'product':
        findings.append(dict(kind='sqlite_not_uniquely_product_catalog', owners=owners))
    elif owners[0][0].rsplit('/', 1)[-1] not in evidence['product_catalog_archives']:
        findings.append(dict(kind='sqlite_owner_not_named_product_catalog', owners=owners))
    for symbol, who in sorted(definers.items()):
        if symbol.startswith(canon('sqlite3')):
            for archive, member in who:
                if classify(archive, roles) != 'product':
                    findings.append(dict(kind='foreign_sqlite_provider', symbol=symbol, archive=archive, member=member))
    for name in evidence.get('dynamic_needed', []):
        if 'sqlite' in name.lower():
            findings.append(dict(kind='system_sqlite_dependency', name=name))
    sdk_defined = {canon(s) for a, t in tables.items() if classify(a, roles) == 'sdk'
                   for row in t.values() for s in row['defined']}
    for archive, member in selected:
        row = tables.get(archive, {}).get(member, dict(undefined=set()))
        for symbol in sorted(row['undefined']):
            if symbol.startswith(canon('sqlite3')):
                # SQLite is owned by ProductCatalog; an unselected SDK vendor copy is not a provider.
                if not any(classify(a, roles) == 'product' for a, _ in definers.get(symbol, [])):
                    findings.append(dict(kind='sqlite_reference_without_product_definer', symbol=symbol, consumer=[archive, member]))
        if classify(archive, roles) == 'sdk':
            continue
        for symbol in sorted(row['undefined'] & sdk_defined):
            if symbol.startswith(canon('sqlite3')):
                continue
            if not any(classify(a, roles) == 'sdk' for a, _ in definers.get(symbol, [])):
                findings.append(dict(kind='sdk_entry_without_selected_sdk_owner', symbol=symbol, consumer=[archive, member]))
    return findings


def sqlite_reference_rows(evidence, canon=lambda s: s):
    """Per-reference evidence for every selected member's undefined sqlite3* symbol.

    Records the selected definers and the installed-but-unselected candidates, so the
    classification is derived from the final map selection, never assumed.
    """
    roles = evidence['roles']
    selected = {tuple(x) for x in evidence['selected']}
    rows, candidates = [], {}
    for archive, table in evidence['archives'].items():
        for member, row in table.items():
            for symbol in row['defined']:
                symbol = canon(symbol)
                if symbol.startswith(canon('sqlite3')):
                    candidates.setdefault(symbol, []).append((archive, member))
    for archive, member in sorted(selected):
        row = evidence['archives'].get(archive, {}).get(member)
        for symbol in sorted(canon(s) for s in (row['undefined'] if row else ())):
            if not symbol.startswith(canon('sqlite3')):
                continue
            both = candidates.get(symbol, [])
            chosen = [list(c) for c in both if c in selected]
            rows.append(dict(symbol=symbol, consumer=[archive, member], selected_definers=chosen,
                selected_roles=sorted({classify(a, roles) for a, _ in chosen}),
                unselected_candidates=[dict(archive=a, member=m, role=classify(a, roles)) for a, m in both if (a, m) not in selected],
                status='resolved_by_selected_product' if chosen and all(classify(a, roles) == 'product' for a, _ in chosen) and len(chosen) == 1 else 'PROBLEM'))
    return rows


NM_OBJECT = re.compile(r'^(?P<path>.+?\.o):\s*(?P<addr>[0-9a-fA-F]*)\s+(?P<kind>[A-Za-z?-])\s+(?P<sym>\S+)\s*$')


def parse_nm_object(text):
    """`nm -A -g` over one loose object file -> a single member row (same shape as an archive member)."""
    row = dict(defined=set(), weak=set(), undefined=set())
    for line in text.splitlines():
        if not line.strip():
            continue
        m = NM_OBJECT.match(line)
        if not m:
            _fail('unrecognised object nm line: ' + line[:120])
        kind = m.group('kind')
        if kind == 'U':
            row['undefined'].add(m.group('sym'))
        elif kind in ('w', 'W', 'v', 'V'):
            row['weak'].add(m.group('sym'))
        elif kind in STRONG:
            row['defined'].add(m.group('sym'))
        elif kind.islower() or kind in ('A', '?', '-'):
            continue
        else:
            _fail('unsupported nm kind ' + kind)
    return row


DYN_SYM = re.compile(r'^\s*\d+:\s+[0-9a-fA-F]+\s+(?:0x[0-9a-fA-F]+|\d+)\s+(?P<type>\w+)\s+(?P<bind>\w+)\s+(?P<vis>\w+)\s+(?P<ndx>\S+)\s+(?P<name>\S+?)(?:\s+\(\d+\))?\s*$')


def parse_dyn_syms(text):
    """`readelf -W --dyn-syms` -> [dict(name, version, bind, ndx, type)] preserving ELF symbol versions."""
    if 'Symbol table' not in text:
        _fail('not a readelf dynamic symbol table')
    rows = []
    for line in text.splitlines():
        if not re.match(r'^\s*\d+:', line):
            continue
        m = DYN_SYM.match(line)
        if not m:
            if re.match(r'^\s*\d+:\s+[0-9a-fA-F]+\s+(?:0x[0-9a-fA-F]+|\d+)\s+\w+\s+\w+\s+\w+\s+\S+\s*$', line):
                continue  # unnamed null-symbol rows carry no name
            _fail('unrecognised dynamic symbol line: ' + line[:120])
        raw = m.group('name')
        name, _, version = raw.partition('@')
        rows.append(dict(name=name, version=version.lstrip('@') or None, bind=m.group('bind'),
                         ndx=m.group('ndx'), type=m.group('type'), vis=m.group('vis'),
                         default='@' not in raw or '@@' in raw))
    return rows


def parse_verneed(text):
    """`readelf -W -V` -> {needed file: [versions]} from the version-needs section only."""
    needs, current, inside = {}, None, False
    for line in text.splitlines():
        if line.startswith('Version needs section'):
            inside = True
            continue
        if line.startswith('Version ') and inside:
            inside = False
        if not inside:
            continue
        f = re.search(r'File:\s*(\S+)', line)
        if f:
            current = f.group(1)
            needs.setdefault(current, [])
            continue
        n = re.search(r'Name:\s*(\S+)', line)
        if n:
            if current is None:
                _fail('version name before file in verneed')
            needs[current].append(n.group(1))
    return needs


def audit_dynamic(dynamic):
    """Final-image dynamic imports/exports and ELF symbol versions.

    Returns (findings, pending). Weak undefined imports and unversioned imports are NOT waived:
    they are listed as pending because proving them needs the exact system DSO exports.
    """
    findings, pending = [], []
    needed, verneed = set(dynamic['needed']), dynamic['verneed']
    for file in sorted(set(verneed) - needed):
        findings.append(dict(kind='verneed_file_not_needed', file=file))
    seen_versions = {v for file in verneed for v in verneed[file]}
    weak, unversioned = [], []
    for sym in dynamic['symbols']:
        if sym['name'].startswith('sqlite3'):
            findings.append(dict(kind='dynamic_sqlite_symbol', symbol=sym['name'], version=sym['version'], ndx=sym['ndx']))
        undefined = sym['ndx'] == 'UND'
        if undefined and sym['version'] and sym['version'] not in seen_versions:
            findings.append(dict(kind='dynamic_version_not_in_verneed', symbol=sym['name'], version=sym['version']))
        if undefined and sym['bind'] == 'WEAK':
            weak.append(sym['name'] + ('@' + sym['version'] if sym['version'] else ''))
        elif undefined and not sym['version']:
            unversioned.append(sym['name'])
    if weak:
        pending.append(dict(kind='weak_undefined_imports_unproven', symbols=sorted(weak)))
    if unversioned:
        pending.append(dict(kind='unversioned_imports_unproven_without_system_dso', count=len(unversioned), symbols=sorted(unversioned)))
    return findings, pending

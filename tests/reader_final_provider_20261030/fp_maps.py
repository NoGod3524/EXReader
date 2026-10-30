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

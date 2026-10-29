"""Read exact retained x64 COFF member/symbol identities; reject unknown formats."""
import struct
from pathlib import PureWindowsPath
from wf07_contract import require


def object_symbols(data, member):
    require(len(data) >= 20, 'short COFF object')
    if data[:4] == b'\0\0\xff\xff':
        require(len(data) >= 56 and data[12:28] == bytes.fromhex('c7a1bad1eebaa94baf20faf66aa4dcb8'),
                'unsupported import/LTCG/anonymous object')
        require(struct.unpack_from('<H', data, 6)[0] == 0x8664, 'non-x64 bigobj')
        pointer, count = struct.unpack_from('<II', data, 48); width = 20
    else:
        machine, sections, _, pointer, count, optional, _ = struct.unpack_from('<HHIIIHH', data)
        require(machine == 0x8664 and sections > 0 and optional == 0, 'unsupported COFF object header')
        width = 18
    end = pointer + count * width
    require(pointer > 0 and count > 0 and end + 4 <= len(data), 'missing/truncated COFF symbol table')
    strings_size = struct.unpack_from('<I', data, end)[0]
    require(strings_size >= 4 and end + strings_size <= len(data), 'COFF string table bounds')
    strings = data[end:end + strings_size]
    records, index = {}, 0
    while index < count:
        offset = pointer + index * width
        raw_name = data[offset:offset + 8]
        if raw_name[:4] == b'\0' * 4:
            start = struct.unpack_from('<I', raw_name, 4)[0]
            require(4 <= start < len(strings) and b'\0' in strings[start:], 'COFF long symbol name bounds')
            name = strings[start:strings.index(b'\0', start)].decode('utf-8')
        else: name = raw_name.split(b'\0', 1)[0].decode('utf-8')
        value = struct.unpack_from('<I', data, offset + 8)[0]
        section = struct.unpack_from('<i' if width == 20 else '<h', data, offset + 12)[0]
        storage, aux = data[offset + width - 2:offset + width]
        require(index + aux < count, 'COFF auxiliary record bounds')
        record = dict(name=name, member=member, storage=storage, undefined=section == 0 and value == 0,
                      weak=storage == 105, section=section)
        if storage == 105:
            require(aux == 1 and record['undefined'], 'unsupported COFF weak definition/auxiliary')
            fallback, search = struct.unpack_from('<II', data, offset + width)
            require(search in (1, 2, 3), 'unsupported COFF weak search mode')
            record.update(fallback_index=fallback, search=search)
        records[index] = record
        index += aux + 1
    external = []
    for record in records.values():
        if record['storage'] not in (2, 105): continue
        if record['weak']:
            fallback = records.get(record['fallback_index'])
            require(fallback is not None and fallback['storage'] in (2, 105), 'unrecognized COFF weak auxiliary fallback')
            record['fallback'] = fallback['name']
        external.append(record)
    # Empty archive members (compiler-generated metadata) are preserved; the
    # complete library/object still must have recognized external symbols.
    return external


def read_symbols(data, filename):
    rows, members = [], []
    if not data.startswith(b'!<arch>\n'):
        member = PureWindowsPath(filename).name
        rows = object_symbols(data, member); members.append(member)
    else:
        offset, longnames = 8, None
        while offset < len(data):
            require(offset + 60 <= len(data) and data[offset + 58:offset + 60] == b'`\n', 'invalid COFF archive member header')
            spelling = data[offset:offset + 16].decode('ascii').strip()
            size_text = data[offset + 48:offset + 58].decode('ascii').strip()
            require(size_text.isdecimal(), 'invalid archive member size')
            size = int(size_text); payload = data[offset + 60:offset + 60 + size]
            require(len(payload) == size, 'truncated archive member')
            if spelling == '//': longnames = payload
            elif spelling not in ('/', '/SYM64/'):
                if spelling.startswith('/') and spelling[1:].isdigit():
                    start = int(spelling[1:]); require(longnames is not None and start < len(longnames), 'archive longname bounds')
                    endings = [i for i in (longnames.find(b'\0', start), longnames.find(b'/\n', start)) if i >= 0]
                    require(endings, 'unterminated archive longname')
                    member = longnames[start:min(endings)].decode('utf-8')
                else:
                    require(not spelling.startswith('#1/'), 'unsupported BSD archive member')
                    member = spelling.removesuffix('/')
                # The actual FreeType .res-named member is converted x64 COFF,
                # not a raw resource stream. Name support never bypasses the
                # same complete object/symbol/auxiliary validation below.
                require(member and member.lower().endswith(('.obj', '.o', '.res')),
                        'unsupported non-object archive member: ' + str(dict(archive=filename, member=member,
                            bytes=len(payload), first_64_bytes_hex=payload[:64].hex())))
                members.append(member); rows.extend(object_symbols(payload, member))
            offset += 60 + size + (size % 2)
        require(offset == len(data), 'archive trailing bytes')
    require(rows and members, 'no recognized external COFF symbols')
    summary = dict(defined=sorted({r['name'] for r in rows if not r['undefined']}),
                   undefined=sorted({r['name'] for r in rows if r['undefined']}),
                   weak=sorted({r['name'] for r in rows if r['weak']}))
    return dict(summary=summary, rows=rows, members=members)


def member_defines(record, member, symbol):
    if '/' in member or '\\' in member:
        matches = [name for name in record['members'] if PureWindowsPath(name) == PureWindowsPath(member)]
    else:
        matches = [name for name in record['members'] if PureWindowsPath(name).name.lower() == member.lower()]
    return len(matches) == 1 and any(row['member'] in matches and row['name'] == symbol and not row['undefined'] for row in record['rows'])

#!/usr/bin/env python3
"""Inspect PE/ELF/Mach-O/ar without loading target code or requiring target tools."""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = ROOT / 'tools/abi/contract.json'


class Binary:
    def __init__(self, data, endian='<'):
        self.data, self.endian = data, endian

    def unpack(self, fmt, offset):
        return struct.unpack_from(self.endian + fmt, self.data, offset)

    def string(self, offset):
        end = self.data.index(b'\0', offset)
        return self.data[offset:end].decode('ascii')


def pe_exports(data):
    b = Binary(data)
    pe, = b.unpack('I', 0x3c)
    if data[pe:pe+4] != b'PE\0\0':
        raise ValueError('invalid PE signature')
    machine, sections, _, _, _, optional_size, _ = b.unpack('HHIIIHH', pe+4)
    optional = pe + 24
    magic, = b.unpack('H', optional)
    if magic not in (0x10b, 0x20b):
        raise ValueError('unsupported PE optional header')
    directory = optional + (112 if magic == 0x20b else 96)
    export_rva, export_size = b.unpack('II', directory)
    table = []
    for i in range(sections):
        offset = optional + optional_size + i * 40
        virtual_size, rva, raw_size, raw = b.unpack('IIII', offset+8)
        table.append((rva, max(virtual_size, raw_size), raw))

    def file_offset(rva):
        for start, size, raw in table:
            if start <= rva < start + size:
                return raw + rva - start
        raise ValueError(f'PE RVA outside sections: {rva}')

    symbols = set()
    if export_rva and export_size:
        export = file_offset(export_rva)
        count, = b.unpack('I', export+24)
        names_rva, = b.unpack('I', export+32)
        names = file_offset(names_rva)
        for i in range(count):
            name_rva, = b.unpack('I', names+i*4)
            symbols.add(b.string(file_offset(name_rva)))
    return [{'format': 'PE', 'machine': hex(machine), 'symbols': symbols}]


def elf_exports(data):
    bits, encoding = data[4], data[5]
    if bits not in (1, 2) or encoding not in (1, 2):
        raise ValueError('unsupported ELF class/encoding')
    b = Binary(data, '<' if encoding == 1 else '>')
    kind, machine = b.unpack('HH', 16)
    if bits == 2:
        section_offset, = b.unpack('Q', 40)
        section_size, count = b.unpack('HH', 58)
        section_fmt, symbol_fmt = 'IIQQQQIIQQ', 'IBBHQQ'
    else:
        section_offset, = b.unpack('I', 32)
        section_size, count = b.unpack('HH', 46)
        section_fmt, symbol_fmt = 'IIIIIIIIII', 'IIIBBH'
    if not count or not section_offset:
        raise ValueError('ELF section table absent/extended; inspect with llvm-nm')
    sections = [b.unpack(section_fmt, section_offset+i*section_size) for i in range(count)]
    symbols = set()
    wanted = 2 if kind == 1 else 11  # relocatable: SYMTAB; shared library: DYNSYM
    if not any(s[1] == wanted for s in sections):
        raise ValueError('ELF symbol table absent')
    for s in sections:
        if s[1] != wanted:
            continue
        strings = sections[s[6]][4]
        if not s[9]:
            raise ValueError('zero ELF symbol entry size')
        for offset in range(s[4], s[4]+s[5], s[9]):
            entry = b.unpack(symbol_fmt, offset)
            name = entry[0]
            info, other, defined = entry[1:4] if bits == 2 else entry[3:6]
            if name and defined and info >> 4 in (1, 2, 10) and other & 3 in (0, 3):
                symbols.add(b.string(strings+name))
    return [{'format': 'ELF', 'machine': hex(machine), 'symbols': symbols}]


def macho_exports(data):
    magic = data[:4]
    endian = '<' if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe') else '>'
    b = Binary(data, endian)
    is64 = magic in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf')
    machine, = b.unpack('I', 4)
    commands, = b.unpack('I', 16)
    offset = 32 if is64 else 28
    symbols = set()
    found = False
    for _ in range(commands):
        command, size = b.unpack('II', offset)
        if size < 8 or offset + size > len(data):
            raise ValueError('invalid Mach-O load command')
        if command == 2:  # LC_SYMTAB, external definitions only
            found = True
            symoff, count, stroff, _ = b.unpack('IIII', offset+8)
            for i in range(count):
                name, flags, section, _, value = b.unpack('IBBHQ' if is64 else 'IBBHI', symoff+i*(16 if is64 else 12))
                # Reject STAB, private extern, undefined and indirect entries.
                if name and not flags & 0xf0 and flags & 1 and flags & 0x0e in (2, 0x0e):
                    symbol = b.string(stroff+name)
                    symbols.add(symbol[1:] if symbol.startswith('_') else symbol)
        offset += size
    if not found:
        raise ValueError('Mach-O LC_SYMTAB absent; stripped export tries require llvm-nm')
    return [{'format': 'Mach-O', 'machine': hex(machine), 'symbols': symbols}]


def inspect_bytes(data):
    if data.startswith(b'MZ'):
        return pe_exports(data)
    if data.startswith(b'\x7fELF'):
        return elf_exports(data)
    if data[:4] in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce'):
        return macho_exports(data)
    if data[:4] in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf', b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'):
        b = Binary(data, '>' if data[0] == 0xca else '<')
        count, = b.unpack('I', 4)
        is64 = data[:4] in (b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca')
        slices = []
        for i in range(count):
            entry = b.unpack('IIQQII' if is64 else 'IIIII', 8+i*(32 if is64 else 20))
            start, size = entry[2:4]
            slices.extend(inspect_bytes(data[start:start+size]))
        if not slices:
            raise ValueError('empty universal binary')
        return slices
    if data.startswith(b'!<arch>\n'):
        groups = {}
        offset = 8
        while offset < len(data):
            header = data[offset:offset+60]
            if len(header) != 60 or header[58:] != b'`\n':
                raise ValueError('invalid ar member header')
            size = int(header[48:58])
            member = data[offset+60:offset+60+size]
            if len(member) != size:
                raise ValueError('truncated ar member')
            name = header[:16].decode('ascii').strip()
            if name.startswith('#1/'):
                n = int(name[3:])
                name, member = member[:n].rstrip(b'\0').decode('utf-8'), member[n:]
            if name not in ('/', '//', '/SYM64/') and not name.startswith('__.SYMDEF'):
                for part in inspect_bytes(member):
                    key = part['machine']
                    groups.setdefault(key, set()).update(part['symbols'])
            offset += 60 + size + size % 2
        if not groups:
            raise ValueError('archive contains no supported object members')
        return [{'format': 'ar', 'machine': key, 'symbols': value} for key, value in sorted(groups.items())]
    raise ValueError('unsupported binary (expected PE, ELF, Mach-O, universal Mach-O or ar)')


def inspect(path, expected):
    data = Path(path).read_bytes()
    slices = []
    for part in inspect_bytes(data):
        symbols = part['symbols']
        slices.append({**part, 'symbols': sorted(symbols), 'symbol_count': len(symbols),
                       'contract_count': len(symbols & expected),
                       'missing': sorted(expected-symbols), 'extra': sorted(symbols-expected)})
    return {'path': str(path), 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'slices': slices}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binaries', type=Path, nargs='+')
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument('--allow-extra', action='store_true', help='require every ABI symbol, permit internal/vendor exports')
    parser.add_argument('--output', type=Path, help='write complete JSON including symbol lists')
    args = parser.parse_args()
    expected = set(json.loads(args.contract.read_text(encoding='utf-8'))['symbols'])
    if not expected:
        parser.error('empty ABI contract')
    results, failed = [], False
    for path in args.binaries:
        try:
            report = inspect(path, expected)
            report['passed'] = all(not p['missing'] and (args.allow_extra or not p['extra']) for p in report['slices'])
            for part in report['slices']:
                print(f"{'PASS' if report['passed'] else 'FAIL'} {path} [{part['machine']}] "
                      f"exports={part['symbol_count']} ABI={part['contract_count']}/{len(expected)} "
                      f"missing={len(part['missing'])} extra={len(part['extra'])}")
        except (OSError, ValueError, IndexError, KeyError, struct.error, UnicodeError) as error:
            report = {'path': str(path), 'passed': False, 'error': str(error)}
            print(f'ERROR {path}: {error}', file=sys.stderr)
        results.append(report)
        failed |= not report['passed']
    if args.output:
        args.output.write_text(json.dumps({'strict': not args.allow_extra, 'results': results}, indent=2)+'\n', encoding='utf-8')
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())

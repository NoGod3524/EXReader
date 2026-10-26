# SPDX-License-Identifier: MIT
"""Read a PE image's export and import tables without any toolchain.

Windows runners do not always expose dumpbin on PATH; parsing the image itself
keeps the evidence independent of the build environment. Only what the linker
actually wrote is reported.
"""
import struct


class PE:
    def __init__(self, path):
        self.data = path.read_bytes()
        data = self.data
        if data[:2] != b'MZ':
            raise ValueError('not a PE image: ' + str(path))
        offset = struct.unpack_from('<I', data, 0x3c)[0]
        if data[offset:offset + 4] != b'PE\0\0':
            raise ValueError('bad PE signature: ' + str(path))
        coff = offset + 4
        self.machine, self.section_count = struct.unpack_from('<HH', data, coff)
        optional_size = struct.unpack_from('<H', data, coff + 16)[0]
        optional = coff + 20
        self.magic = struct.unpack_from('<H', data, optional)[0]
        self.subsystem = struct.unpack_from('<H', data, optional + 68)[0]
        if self.magic == 0x20b:
            self.image_base = struct.unpack_from('<Q', data, optional + 24)[0]
        else:
            self.image_base = struct.unpack_from('<I', data, optional + 28)[0]
        count_rva = struct.unpack_from('<I', data, optional + 108)[0]
        directories = optional + 112
        self.directories = []
        for index in range(min(count_rva, 16)):
            self.directories.append(struct.unpack_from('<II', data, directories + index * 8))
        self.sections = []
        section = optional + optional_size
        for index in range(self.section_count):
            base = section + index * 40
            name = data[base:base + 8].rstrip(b'\0').decode('latin-1')
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
                '<IIII', data, base + 8)
            self.sections.append((name, virtual_address, max(virtual_size, raw_size), raw_pointer))

    def offset_of(self, rva):
        for _name, virtual_address, size, raw_pointer in self.sections:
            if virtual_address <= rva < virtual_address + size:
                return raw_pointer + (rva - virtual_address)
        raise ValueError('rva outside every section: ' + hex(rva))

    def exports(self):
        if not self.directories or self.directories[0][0] == 0:
            return []
        rva, _size = self.directories[0]
        base = self.offset_of(rva)
        count = struct.unpack_from('<I', self.data, base + 24)[0]
        names_rva = struct.unpack_from('<I', self.data, base + 32)[0]
        names = self.offset_of(names_rva)
        found = []
        for index in range(count):
            name_rva = struct.unpack_from('<I', self.data, names + index * 4)[0]
            start = self.offset_of(name_rva)
            end = self.data.index(b'\0', start)
            found.append(self.data[start:end].decode('latin-1'))
        return found

    def imports(self):
        if len(self.directories) < 2 or self.directories[1][0] == 0:
            return []
        rva, _size = self.directories[1]
        descriptor = self.offset_of(rva)
        found = []
        while True:
            if self.data[descriptor:descriptor + 20] == b'\0' * 20:
                break
            name_rva = struct.unpack_from('<I', self.data, descriptor + 12)[0]
            if name_rva:
                start = self.offset_of(name_rva)
                end = self.data.index(b'\0', start)
                found.append(self.data[start:end].decode('latin-1'))
            descriptor += 20
        return found

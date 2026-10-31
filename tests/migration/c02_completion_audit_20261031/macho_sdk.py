# SPDX-License-Identifier: MIT
"""Independent 64LE Mach-O SDK/signature inspection.
Primary layouts: Apple cctools include/mach-o/loader.h and xnu kern/cs_blobs.h.
No native verifier is loaded or executed.
"""
import hashlib
import struct
from protocols import need, sha

def _u(raw, offset, kind="<I"):
    size = struct.calcsize(kind)
    need(0 <= offset and offset+size <= len(raw),"macho-sdk-integer-bounds")
    return struct.unpack_from(kind,raw,offset)[0]

def _be(raw, offset):
    return _u(raw,offset,">I")

def _code_directory(raw, code, offset):
    need(len(code) >= 44 and _be(code,0) == 0xfade0c02 and _be(code,4) == len(code),"macho-sdk-code-directory-blob")
    fields = dict(version=_be(code,8),flags=_be(code,12),hash_offset=_be(code,16),
                  identifier_offset=_be(code,20),special_slots=_be(code,24),code_slots=_be(code,28),
                  code_limit32=_be(code,32),hash_size=code[36],hash_type=code[37],
                  platform=code[38],page_exponent=code[39],spare2=_be(code,40))
    version = fields["version"]
    minimum = 44
    if version >= 0x20100:
        minimum = 48
        fields["scatter_offset"] = _be(code,44)
    if version >= 0x20200:
        minimum = 52
        fields["team_offset"] = _be(code,48)
    if version >= 0x20300:
        minimum = 64
        fields.update(spare3=_be(code,52),code_limit64=_u(code,56,">Q"))
    if version >= 0x20400:
        minimum = 88
        fields.update(exec_base=_u(code,64,">Q"),exec_limit=_u(code,72,">Q"),exec_flags=_u(code,80,">Q"))
    if version >= 0x20500:
        minimum = 96
        fields.update(runtime=_be(code,88),preencrypt_offset=_be(code,92))
    if version >= 0x20600:
        minimum = 108
        fields.update(linkage_hash=code[96],linkage_type=code[97],
                      linkage_subtype=_u(code,98,">H"),linkage_offset=_be(code,100),linkage_size=_be(code,104))
    need(len(code) >= minimum and minimum <= fields["identifier_offset"] < len(code),"macho-sdk-cd-header-identifier")
    start = fields["identifier_offset"]
    end = code.find(b"\0",start)
    need(end >= start and end-start <= 1024,"macho-sdk-cd-identifier-terminated")
    fields["identifier"] = code[start:end].decode("utf-8","backslashreplace")
    limit = fields.get("code_limit64",0) or fields["code_limit32"]
    exponent = fields["page_exponent"]
    supported = fields["hash_type"] == 2 and fields["hash_size"] == 32 and 0 < exponent < 31 and not fields.get("scatter_offset",0)
    fields.update(bytes=len(code),sha256=sha(code),code_limit=limit,page_hashes_supported=supported)
    if supported:
        page = 1 << exponent
        count = (limit+page-1)//page
        hashes = fields["hash_offset"]
        need(limit == offset and count == fields["code_slots"] and
             hashes-fields["special_slots"]*32 >= minimum and hashes+count*32 <= len(code),
             "macho-sdk-cd-full-prefix-hash-coverage")
        verified = 0
        for number in range(count):
            digest = hashlib.sha256(raw[number*page:min((number+1)*page,limit)]).digest()
            if digest == code[hashes+number*32:hashes+(number+1)*32]:
                verified += 1
        fields.update(page_bytes=page,page_hashes_verified=verified,
                      all_page_hashes_valid=verified == count)
    return fields

def inspect_macho(raw):
    need(isinstance(raw,bytes) and len(raw) >= 32 and raw[:4] == b"\xcf\xfa\xed\xfe","macho-sdk-only-64le")
    count,total = _u(raw,16),_u(raw,20)
    need(0 < count <= 1024 and 32+total <= len(raw),"macho-sdk-command-table-bounds")
    commands, signatures, linkedit = [],[],[]
    position = 32
    for _ in range(count):
        kind,size = _u(raw,position),_u(raw,position+4)
        need(size >= 8 and size % 8 == 0 and position+size <= 32+total,"macho-sdk-command-size")
        command = dict(offset=position,kind=kind,bytes=size,sha256=sha(raw[position:position+size]))
        if kind == 0x19:
            need(size >= 72 and size == 72+80*_u(raw,position+64),"macho-sdk-segment64-size")
            name = raw[position+8:position+24].split(b"\0",1)[0].decode("ascii")
            command["segment"] = dict(name=name,vmaddr=_u(raw,position+24,"<Q"),vmsize=_u(raw,position+32,"<Q"),
                fileoff=_u(raw,position+40,"<Q"),filesize=_u(raw,position+48,"<Q"),maxprot=_u(raw,position+56),
                initprot=_u(raw,position+60),sections=_u(raw,position+64),flags=_u(raw,position+68))
            sections = []
            for index in range(command["segment"]["sections"]):
                entry = position+72+80*index
                sections.append(dict(name=raw[entry:entry+16].split(b"\0",1)[0].decode("ascii"),
                    segment=raw[entry+16:entry+32].split(b"\0",1)[0].decode("ascii"),
                    address=_u(raw,entry+32,"<Q"),size=_u(raw,entry+40,"<Q"),
                    offset=_u(raw,entry+48),flags=_u(raw,entry+64)))
            command["section_table"] = sections
            if name == "__LINKEDIT":
                linkedit.append(command)
        elif kind == 0x1b:
            need(size == 24,"macho-sdk-uuid-command-size")
            command["uuid"] = raw[position+8:position+24].hex()
        elif kind == 0xd:
            need(size >= 24,"macho-sdk-id-dylib-command-size")
            name_offset = _u(raw,position+8)
            need(24 <= name_offset < size,"macho-sdk-id-dylib-name-offset")
            end = raw.find(b"\0",position+name_offset,position+size)
            need(end >= position+name_offset,"macho-sdk-id-dylib-name-terminated")
            command.update(install_name=raw[position+name_offset:end].decode("utf-8"),
                           current_version=_u(raw,position+16),compatibility_version=_u(raw,position+20))
        elif kind == 0x1d:
            need(size == 16,"macho-sdk-code-signature-command-size")
            command.update(dataoff=_u(raw,position+8),datasize=_u(raw,position+12))
            signatures.append(command)
        commands.append(command)
        position += size
    need(position == 32+total and len(signatures) == len(linkedit) == 1,"macho-sdk-unique-signature-linkedit")
    signature = signatures[0]
    offset,size = signature["dataoff"],signature["datasize"]
    need(offset >= position and size >= 12 and offset+size <= len(raw),"macho-sdk-signature-file-range")
    blob = raw[offset:offset+size]
    magic,length,entries = _be(blob,0),_be(blob,4),_be(blob,8)
    need(magic == 0xfade0cc0 and entries <= 64 and 12+entries*8 <= length <= len(blob),
         "macho-sdk-superblob-bounds")
    blobs,intervals = [],[]
    for number in range(entries):
        slot,start = _be(blob,12+number*8),_be(blob,16+number*8)
        need(start >= 12+entries*8 and start+8 <= length,"macho-sdk-subblob-start")
        submagic,sublength = _be(blob,start),_be(blob,start+4)
        need(sublength >= 8 and start+sublength <= length and
             all(start >= end or start+sublength <= before for before,end in intervals),"macho-sdk-subblob-overlap-bounds")
        intervals.append((start,start+sublength))
        data = blob[start:start+sublength]
        value = dict(slot=slot,offset=start,magic=submagic,bytes=sublength,sha256=sha(data))
        if submagic == 0xfade0c02:
            value["code_directory"] = _code_directory(raw,data,offset)
        else:
            value["prefix_hex"] = data[:64].hex()
        blobs.append(value)
    return dict(bytes=len(raw),sha256=sha(raw),cpu=_u(raw,4),subcpu=_u(raw,8),filetype=_u(raw,12),
                header_flags=_u(raw,24),header_reserved=_u(raw,28),command_bytes=total,commands=commands,
                signature=dict(command=signature,superblob_bytes=length,blobs=blobs,
                               padding_bytes=len(blob)-length,padding_zero=not any(blob[length:]),
                               file_tail_bytes=len(raw)-(offset+size)),linkedit=linkedit[0])

def sdk_pair_diagnostic(original,bundled):
    before,after = inspect_macho(original),inspect_macho(bundled)
    regions = []
    position = changed = 0
    while position < min(len(original),len(bundled)):
        if original[position] == bundled[position]:
            position += 1
            continue
        start = position
        while position < min(len(original),len(bundled)) and original[position] != bundled[position]:
            position += 1
        changed += position-start
        if len(regions) < 160:
            regions.append(dict(start=start,end=position,original_hex=original[start:min(position,start+32)].hex(),
                                bundled_hex=bundled[start:min(position,start+32)].hex()))
    if len(original) != len(bundled):
        regions.append(dict(start=min(len(original),len(bundled)),original_end=len(original),bundled_end=len(bundled)))
    return dict(scope="diagnostic-only",byte_identical=original == bundled,changed_bytes=changed,
                difference_regions=regions,original=before,bundled=after)

def bind_sdk(original: bytes,bundled: bytes):
    if original == bundled:
        inspect_macho(original)
        return dict(binding="exact-bytes",sha256=sha(original),bytes=len(original))
    raise ValueError("macho-sdk-resigning-profile-awaits-original-byte-diagnostics")

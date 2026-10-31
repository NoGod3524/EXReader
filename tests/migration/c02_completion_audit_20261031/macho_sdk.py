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
        need(len(code) >= minimum,"macho-sdk-cd-linkage-header")
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


def _only(values,label):
    need(len(values) == 1,label)
    return values[0]

def _sdk_layout(raw,layout):
    need(layout["cpu"] == 0x100000c and layout["subcpu"] == 0 and layout["filetype"] == 6,
         "macho-sdk-profile-arm64-dylib")
    commands = layout["commands"]
    text = _only([item for item in commands if item.get("segment",{}).get("name") == "__TEXT"],
                 "macho-sdk-unique-text")
    code = _only([item for item in text["section_table"] if item["name"] == "__text"],
                 "macho-sdk-unique-text-section")
    identity = _only([item for item in commands if item["kind"] == 0xd],"macho-sdk-unique-install-name")
    uuid = _only([item for item in commands if item["kind"] == 0x1b],"macho-sdk-unique-uuid")
    need(identity["install_name"] == "@rpath/libexreader.1.dylib" and
         identity["current_version"] == 0x32a00 and identity["compatibility_version"] == 0x10000,
         "macho-sdk-frozen-sdk342-install-name")
    segment = text["segment"]
    need(segment["fileoff"] == segment["vmaddr"] == 0 and segment["maxprot"] == segment["initprot"] == 5 and
         0 < segment["filesize"] <= layout["signature"]["command"]["dataoff"] and
         code["segment"] == "__TEXT" and code["flags"] == 0x80000400 and
         32+layout["command_bytes"] <= code["offset"] < code["offset"]+code["size"] <= segment["filesize"],
         "macho-sdk-text-code-range")
    signature,linkedit = layout["signature"],layout["linkedit"]["segment"]
    offset = signature["command"]["dataoff"]
    need(offset % 16 == 0 and signature["file_tail_bytes"] == 0 and
         signature["command"]["datasize"] == len(raw)-offset and
         0 <= linkedit["fileoff"] < offset and linkedit["filesize"] == len(raw)-linkedit["fileoff"] and
         linkedit["vmsize"] == (linkedit["filesize"]+0x3fff)//0x4000*0x4000 and
         linkedit["maxprot"] == linkedit["initprot"] == 1 and
         linkedit["sections"] == linkedit["flags"] == 0,
         "macho-sdk-signature-tail-linkedit-size")
    for item in commands:
        value = item.get("segment")
        if value and value["name"] != "__LINKEDIT":
            need(value["fileoff"]+value["filesize"] <= linkedit["fileoff"],"macho-sdk-nonlinkedit-file-range")
    return text,code,identity,uuid

def _signature_profile(raw,layout,resigned):
    text,section,identity,uuid = _sdk_layout(raw,layout)
    signature = layout["signature"]
    expected_slots = [0,2,0x10000] if resigned else [0]
    need([item["slot"] for item in signature["blobs"]] == expected_slots,"macho-sdk-signature-slots")
    cursor = 12+8*len(expected_slots)
    for item in signature["blobs"]:
        need(item["offset"] == cursor,"macho-sdk-signature-packed-blobs")
        cursor += item["bytes"]
    need(cursor == signature["superblob_bytes"] and signature["padding_zero"],
         "macho-sdk-signature-padding")
    entry = signature["blobs"][0]
    need(entry["magic"] == 0xfade0c02 and "code_directory" in entry,"macho-sdk-primary-code-directory")
    value = entry["code_directory"]
    need(value["version"] == 0x20400 and value["flags"] == (2 if resigned else 0x20002) and
         value["hash_type"] == 2 and value["hash_size"] == 32 and value["page_exponent"] == 12 and
         value["platform"] == value["spare2"] == value["scatter_offset"] == value["team_offset"] == 0 and
         value["spare3"] == value["code_limit64"] == value["exec_base"] == value["exec_flags"] == 0,
         "macho-sdk-supported-code-directory")
    need(value["page_hashes_supported"] and value["all_page_hashes_valid"] and
         value["page_hashes_verified"] == value["code_slots"],"macho-sdk-cd-page-hashes")
    special = 2 if resigned else 0
    identifier = value["identifier"]
    uuid_identifier = "libexreader-55554944"+uuid["uuid"]
    need(identifier in ("libexreader.1","libexreader.3",uuid_identifier) if resigned else
         identifier == "libexreader.1.dylib","macho-sdk-signature-identifier")
    expected_limit = text["segment"]["filesize"] if resigned else section["size"]
    need(value["exec_limit"] == expected_limit,"macho-sdk-code-directory-executable-size")
    need(value["identifier_offset"] == 88 and value["special_slots"] == special and
         value["hash_offset"] == 88+len(identifier.encode("ascii"))+1+special*32 and
         value["bytes"] == value["hash_offset"]+value["code_slots"]*32,
         "macho-sdk-code-directory-packed-layout")
    location = signature["command"]["dataoff"]+entry["offset"]
    directory = raw[location:location+entry["bytes"]]
    if resigned:
        requirements = bytes.fromhex("fade0c010000000c00000000")
        cms = bytes.fromhex("fade0b0100000008")
        for item,expected in zip(signature["blobs"][1:],(requirements,cms)):
            start = signature["command"]["dataoff"]+item["offset"]
            need(raw[start:start+item["bytes"]] == expected,"macho-sdk-empty-ad-hoc-signature-metadata")
        hashes = value["hash_offset"]
        need(directory[hashes-32:hashes] == bytes(32) and
             directory[hashes-64:hashes-32] == hashlib.sha256(requirements).digest(),
             "macho-sdk-requirements-special-slot")
        # Only the allocation profiles observed in both original 99999 SDK ZIPs.
        expected_padding = 18011 if identifier == uuid_identifier else 18002
        need(signature["padding_bytes"] == expected_padding and signature["command"]["datasize"] % 16 == 0,
             "macho-sdk-observed-ad-hoc-allocation")
    else:
        need(signature["padding_bytes"] == 0,"macho-sdk-linker-signature-exact-length")
    return dict(code_pages=value["code_slots"],code_directory_sha256=entry["sha256"],
                identifier=identifier,signature_offset=signature["command"]["dataoff"],
                signature_bytes=signature["command"]["datasize"],exec_limit=expected_limit,
                linkedit_fileoff=layout["linkedit"]["segment"]["fileoff"])

def _normalized_prefix(raw,layout):
    end = layout["signature"]["command"]["dataoff"]
    ranges = [(layout["linkedit"]["offset"]+32,8),
              (layout["linkedit"]["offset"]+48,8),
              (layout["signature"]["command"]["offset"]+12,4)]
    result = bytearray(raw[:end])
    for offset,size in ranges:
        need(32 <= offset and offset+size <= 32+layout["command_bytes"],"macho-sdk-normalized-field-bounds")
        result[offset:offset+size] = bytes(size)
    return bytes(result),[dict(offset=offset,bytes=size) for offset,size in ranges]

def bind_sdk(original: bytes,bundled: bytes):
    """Bind an authenticated SDK3.42 original to its exact bytes or observed ad-hoc re-signing."""
    before = inspect_macho(original)
    before_signature = _signature_profile(original,before,False)
    if original == bundled:
        return dict(binding="exact-bytes",original_sha256=sha(original),bundled_sha256=sha(bundled),
                    bytes=len(original),all_code_pages_verified=True,original=before_signature,bundled=before_signature)
    after = inspect_macho(bundled)
    after_signature = _signature_profile(bundled,after,True)
    need(before_signature["signature_offset"] == after_signature["signature_offset"],
         "macho-sdk-resigning-moved-signature")
    first,ranges = _normalized_prefix(original,before)
    second,other_ranges = _normalized_prefix(bundled,after)
    need(ranges == other_ranges and first == second,"macho-sdk-resigning-changed-payload")
    return dict(binding="verified-ad-hoc-resign",original_sha256=sha(original),bundled_sha256=sha(bundled),
                original_bytes=len(original),bundled_bytes=len(bundled),all_code_pages_verified=True,
                normalized_prefix_sha256=sha(first),prefix_bytes=len(first),
                retained_linkedit_bytes=len(first)-before_signature["linkedit_fileoff"],
                mutable_prefix_fields=ranges,original=before_signature,bundled=after_signature)

def _rehash_code_pages(raw):
    """Negative-control helper: make altered payload pages internally self-consistent."""
    layout = inspect_macho(raw)
    entry = layout["signature"]["blobs"][0]
    value = entry["code_directory"]
    need(value["hash_type"] == 2 and value["hash_size"] == 32 and value["page_exponent"] == 12,
         "macho-sdk-negative-control-page-format")
    result = bytearray(raw)
    location = layout["signature"]["command"]["dataoff"]+entry["offset"]+value["hash_offset"]
    for number in range(value["code_slots"]):
        start = number*4096
        result[location+number*32:location+(number+1)*32] = hashlib.sha256(
            raw[start:min(start+4096,value["code_limit"])]).digest()
    return bytes(result)

def sdk_negative_variants(original: bytes,bundled: bytes):
    """Yield byte pairs for Actions original-ZIP re-packaging; no filesystem or native execution."""
    bind_sdk(original,bundled)
    before,after = inspect_macho(original),inspect_macho(bundled)
    text = _only([item for item in after["commands"] if item.get("segment",{}).get("name") == "__TEXT"],
                 "macho-sdk-negative-text")
    section = _only([item for item in text["section_table"] if item["name"] == "__text"],
                    "macho-sdk-negative-text-section")
    code_offset = section["offset"]+min(64,section["size"]-1)
    def flip(raw,offset):
        need(0 <= offset < len(raw),"macho-sdk-negative-byte-bounds")
        changed = bytearray(raw)
        changed[offset] ^= 1
        return bytes(changed)
    def variant(name,first,second):
        return dict(name=name,original=first,bundled=second)
    changed = flip(bundled,code_offset)
    yield variant("sdk-code-byte",original,changed)
    yield variant("sdk-code-byte-rehashed",original,_rehash_code_pages(changed))
    changed = flip(bundled,after["linkedit"]["segment"]["fileoff"]+8)
    yield variant("sdk-linkedit-payload-rehashed",original,_rehash_code_pages(changed))
    changed = flip(original,code_offset)
    yield variant("sdk-original-payload-rehashed",_rehash_code_pages(changed),bundled)
    entry = after["signature"]["blobs"][0]
    hash_offset = after["signature"]["command"]["dataoff"]+entry["offset"]+entry["code_directory"]["hash_offset"]
    yield variant("sdk-forged-page-hash",original,flip(bundled,hash_offset))
    changed = bytearray(bundled)
    struct.pack_into("<I",changed,after["signature"]["command"]["offset"]+8,len(bundled)+16)
    yield variant("sdk-signature-out-of-bounds",original,bytes(changed))
    changed = bytearray(bundled)
    struct.pack_into("<Q",changed,after["linkedit"]["offset"]+48,len(bundled)+1)
    yield variant("sdk-linkedit-out-of-bounds",original,bytes(changed))
    changed = bytearray(bundled)
    struct.pack_into("<Q",changed,after["linkedit"]["offset"]+32,after["linkedit"]["segment"]["vmsize"]+0x4000)
    yield variant("sdk-linkedit-vmsize-rehashed",original,_rehash_code_pages(bytes(changed)))

def sdk_negative_controls(original: bytes,bundled: bytes):
    """Actions check companion; whole-ZIP callers retain and independently audit each yielded variant."""
    records = []
    for candidate in sdk_negative_variants(original,bundled):
        try:
            bind_sdk(candidate["original"],candidate["bundled"])
        except (ValueError,UnicodeError,struct.error) as error:
            records.append(dict(name=candidate["name"],rejected=True,reason=str(error),
                original_sha256=sha(candidate["original"]),bundled_sha256=sha(candidate["bundled"])))
        else:
            raise ValueError("macho-sdk-negative-control-accepted:"+candidate["name"])
    need(len(records) == 8,"macho-sdk-negative-control-count")
    return dict(cases=len(records),failed=0,controls=records)

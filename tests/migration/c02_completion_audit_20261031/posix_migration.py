# SPDX-License-Identifier: MIT
"""Pure independent POSIX migration metadata/floor/head decoding.

Inputs are raw bytes and independently captured fstat rows. No native provider is
loaded. Payload bytes remain opaque: a real-owner adapter must validate INPUT and
PREPARED semantics and journal ACKs separately. audit_transaction does not infer
or advance a caller's exact descriptor/CAS.
"""
import posixpath
import re
from protocols import need, sha, hexadecimal, integer, history
from posix_protocols import (ZERO, u64, native_id, digest_field, sealed, binding,
                             states, metadata, observed_id, absolute_path, route)

MAX_GENERATION = 2**64-1
MAX_LINES = 256

def _nonzero(value, label):
    need(hexadecimal(value,64) and value != ZERO, label)
    return value

def _identity(value, label):
    need(len(value) == 2 and all(integer(v) and v < 2**64 for v in value) and value[1] > 0, label)
    return value

def _observed(raw, name, row, euid):
    need(isinstance(raw,bytes) and isinstance(name,str) and "/" not in name and
         name not in ("",".","..") and posixpath.basename(row["path"]) == name,
         "pm-final-record-observed-name")
    identity = metadata(row,euid)
    need(row["bytes"] == len(raw) and row["sha256"] == sha(raw), "pm-actual-fstat-bytes-digest")
    return identity

def final_name(phase, generation, input_sha, slot=0):
    need(type(generation) is int and 1 <= generation <= MAX_GENERATION, "pm-generation")
    _nonzero(input_sha,"pm-input-sha")
    need(type(phase) is int and phase in (1,2,3) and type(slot) is int, "pm-phase-slot-type")
    if phase == 3:
        need(1 <= slot <= MAX_LINES, "pm-floor-slot")
        return f"floor-{generation:016x}-{slot:03d}"
    need(slot == 0, "pm-nonfloor-slot-zero")
    return f"{'input' if phase == 1 else 'prepared'}-{generation:016x}-{input_sha}"

def head_name(generation,input_sha):
    final_name(1,generation,input_sha)
    return f"commit-head-{generation:016x}-{input_sha}"

def metadata_envelope(raw, name, observed, euid):
    identity = _observed(raw,name,observed,euid)
    need(568+1+64 <= len(raw) <= 568+65536+64 and raw[:8] == b"PC02M001", "pm-envelope-size-magic")
    phase,generation,count = u64(raw,8),u64(raw,16),u64(raw,24)
    need(count == len(raw)-632 and native_id(raw,32) == identity, "pm-envelope-payload-size-self-id")
    origin_raw = raw[48:352]
    origin = binding(origin_raw)
    for key in ("root","parent","target","lease","state","identity"):
        _identity(origin[key],"pm-origin-native-"+key)
    input_sha = _nonzero(digest_field(raw,352),"pm-envelope-input")
    pending = digest_field(raw,416)
    slot = u64(raw,480)
    payload_sha = _nonzero(digest_field(raw,488),"pm-envelope-payload-sha")
    head_id = _identity(native_id(raw,552),"pm-envelope-registered-head-id")
    need(name == final_name(phase,generation,input_sha,slot), "pm-canonical-final-metadata-name")
    payload = raw[568:-64]
    seal = digest_field(raw,len(raw)-64)
    need(sha(raw[:-64]) == seal and sha(payload) == payload_sha, "pm-envelope-payload-and-outer-seals")
    if phase == 1:
        need(pending == ZERO and payload_sha == input_sha, "pm-input-original-payload")
    else:
        _nonzero(pending,"pm-exact-original-b-seal")
    need(origin["generation"] == generation-1, "pm-origin-previous-generation")
    return dict(phase=phase,generation=generation,input=input_sha,pending=pending,slot=slot,
                identity=identity,head_identity=head_id,origin=origin,origin_raw=origin_raw,
                payload=payload,payload_sha256=payload_sha,seal=seal,file_sha256=sha(raw))

def floor_payload(raw, expected_manifest=None, *, profile="production-native-ack"):
    need(profile in ("production-native-ack","component"), "pm-explicit-floor-profile")
    expected_size = 352 if profile == "production-native-ack" else 272
    need(isinstance(raw,bytes) and len(raw) == expected_size, "pm-floor-explicit-profile-size")
    previous_count,next_count = u64(raw,0),u64(raw,136)
    need(previous_count < MAX_LINES and next_count == previous_count+1, "pm-floor-next-count")
    previous_line,previous_chain = digest_field(raw,8),digest_field(raw,72)
    next_line = _nonzero(digest_field(raw,144),"pm-floor-next-line")
    manifest = _nonzero(digest_field(raw,208),"pm-floor-manifest")
    if previous_count == 0:
        need(previous_line == previous_chain == ZERO, "pm-empty-floor-zero-line-chain")
    else:
        _nonzero(previous_line,"pm-floor-previous-line")
        _nonzero(previous_chain,"pm-floor-previous-whole-file")
    if expected_manifest is not None:
        need(manifest == expected_manifest, "pm-floor-exact-manifest")
    ack_id = _identity(native_id(raw,272),"pm-floor-actual-ack-id") if expected_size == 352 else None
    ack_sha = _nonzero(digest_field(raw,288),"pm-floor-whole-ack-sha") if expected_size == 352 else None
    return dict(previous_count=previous_count,previous_line=previous_line,previous_chain=previous_chain,
                count=next_count,last_line_sha256=next_line,manifest=manifest,profile=profile,
                ack_identity=ack_id,ack_sha256=ack_sha)

def native_ack(raw, name, observed, euid):
    identity = _observed(raw,name,observed,euid)
    need(361 <= len(raw) <= 296+2047+64 and raw[:8] == b"PC02ACK1", "pm-ack-wire-size-magic")
    count,size = u64(raw,24),u64(raw,224)
    need(1 <= count <= MAX_LINES and name == f"ack-{count:03d}" and
         size == len(raw)-360 and native_id(raw,8) == identity, "pm-ack-name-size-actual-self-id")
    manifest = _nonzero(digest_field(raw,32),"pm-ack-manifest")
    input_sha = _nonzero(digest_field(raw,96),"pm-ack-original-input")
    pending = _nonzero(digest_field(raw,160),"pm-ack-original-b-seal")
    line_sha = _nonzero(digest_field(raw,232),"pm-ack-line-sha")
    line = raw[296:-64]
    need(b"\0" not in line and sha(line) == line_sha and
         sha(raw[:-64]) == digest_field(raw,len(raw)-64), "pm-ack-canonical-line-and-seal")
    return dict(count=count,identity=identity,manifest=manifest,input=input_sha,pending=pending,
                line_sha256=line_sha,line=line,file_sha256=sha(raw))

def committed_head(raw, name, observed, euid):
    identity = _observed(raw,name,observed,euid)
    need(464 <= len(raw) <= 464+272*MAX_LINES and (len(raw)-464) % 272 == 0,
         "pm-head-complete-records-only")
    seal = sealed(raw[:464],b"PC02F001",400)
    generation = u64(raw,8)
    input_sha = _nonzero(digest_field(raw,16),"pm-head-input")
    origin_raw = raw[80:384]
    origin = binding(origin_raw)
    for key in ("root","parent","target","lease","state","identity"):
        _identity(origin[key],"pm-head-origin-native-"+key)
    need(name == head_name(generation,input_sha) and native_id(raw,384) == identity,
         "pm-head-final-name-self-id")
    need(origin["generation"] == generation-1, "pm-head-origin-generation")
    records = []
    previous = seal
    for offset in range(464,len(raw),272):
        record = raw[offset:offset+272]
        digest = sealed(record,b"PC02H001",208)
        count = u64(record,8)
        line = _nonzero(digest_field(record,16),"pm-head-line")
        floor = _nonzero(digest_field(record,80),"pm-head-whole-floor-file")
        need(count == len(records)+1 and digest_field(record,144) == previous, "pm-head-count-seal-chain")
        records.append(dict(count=count,last_line_sha256=line,chain_sha256=floor,seal=digest))
        previous = digest
    return dict(generation=generation,input=input_sha,identity=identity,origin=origin,
                origin_raw=origin_raw,header_seal=seal,records=records,count=len(records),
                file_sha256=sha(raw))

def exact_floor(actual, expected):
    """Strict observational CAS. Never substitutes a newer observed floor."""
    for label,value in (("actual",actual),("expected",expected)):
        need(isinstance(value,dict) and type(value.get("count")) is int and
             0 <= value["count"] <= MAX_LINES, "pm-explicit-floor-cas-"+label)
        _nonzero(value.get("manifest"),"pm-floor-cas-manifest-"+label)
        for key in ("last_line_sha256","chain_sha256"):
            need(hexadecimal(value.get(key),64), "pm-floor-cas-canonical-"+label+"-"+key)
            need(value[key] == ZERO if value["count"] == 0 else value[key] != ZERO,
                 "pm-floor-cas-empty-or-protected-"+label+"-"+key)
    need(all(actual[key] == expected[key] for key in
             ("count","manifest","last_line_sha256","chain_sha256")), "pm-exact-floor-cas")
    return True

def _bind_acknowledgements(files, acknowledgements, euid, exact, floors, expected_source, prefix):
    need(isinstance(acknowledgements,dict) and len(acknowledgements) <= MAX_LINES and
         all(type(slot) is int for slot in acknowledgements) and
         set(acknowledgements) == set(range(1,len(acknowledgements)+1)), "pm-complete-actual-ack-inventory")
    need(hexadecimal(expected_source,40) and expected_source != "0"*40, "pm-qualified-journal-producer-source")
    prefix = _prefix(prefix)
    captured = {path for path in files if posixpath.dirname(path) == prefix.rstrip("/") and
                posixpath.basename(path).startswith("ack-")}
    need(captured == {entry["path"] for entry in acknowledgements.values()},
         "pm-all-complete-ack-files-included")
    decoded = []
    for slot in range(1,len(acknowledgements)+1):
        entry = acknowledgements[slot]
        path = entry["path"]
        need(isinstance(path,str) and not path.startswith("/") and posixpath.normpath(path) == path and
             all(part not in ("",".","..") for part in path.split("/")) and path in files,
             "pm-original-ack-byte-path")
        record = native_ack(files[path],posixpath.basename(path),entry["observed"],euid)
        need(record["count"] == slot and record["manifest"] == exact["manifest"] and
             record["input"] == exact["input"] and record["pending"] == exact["seal"],
             "pm-every-complete-ack-original-transaction")
        decoded.append(record)
    lines = [row["line"] for row in decoded]
    journal = history(lines,expected_source)
    if lines:
        need(sha(lines[0]) == exact["manifest"], "pm-original-ack-manifest-line")
    need(len(floors) <= len(decoded), "pm-floor-cannot-exceed-real-ack-prefix")
    for floor in floors:
        ack = decoded[floor["count"]-1]
        need(floor["ack_identity"] == ack["identity"] and floor["ack_sha256"] == ack["file_sha256"] and
             floor["last_line_sha256"] == ack["line_sha256"], "pm-floor-actual-ack-fstat-raw-and-line")
    return decoded,journal

def _exact_begin(history, exact):
    need(isinstance(exact,dict) and type(exact.get("generation")) is int and
         1 <= exact["generation"] <= MAX_GENERATION, "pm-explicit-native-descriptor")
    for key in ("seal","manifest","input"):
        _nonzero(exact.get(key),"pm-descriptor-"+key)
    last = history[-1]
    need(last["kind"] in ("B","C") and last["generation"] == exact["generation"],
         "pm-descriptor-is-current-generation")
    index = len(history)-1 if last["kind"] == "B" else len(history)-2
    need(index > 0, "pm-b-has-previous-clean")
    begin = history[index]
    need(begin["kind"] == "B" and all(begin[key] == exact[key] for key in
         ("generation","seal","manifest","input")), "pm-exact-original-b-descriptor")
    previous = history[index-1]
    need(previous["kind"] in ("I","C") and previous["generation"]+1 == begin["generation"] and
         previous["target"] == begin["target"], "pm-b-independent-previous-clean")
    return begin,previous

def _origin(origin, raw, current, current_raw, begin, previous, last):
    for key in ("root","parent","lease","state","route"):
        need(origin[key] == current[key], "pm-origin-live-binding-"+key)
    need(origin["generation"] == begin["generation"]-1 == previous["generation"] and
         origin["grant"] == previous["seal"] and origin["target"] == begin["target"],
         "pm-origin-actual-b-previous-clean-target")
    if current["generation"] == origin["generation"]:
        need(raw == current_raw, "pm-exact-unchanged-original-binding")
    else:
        need(last["kind"] == "C" and current["generation"] == begin["generation"] and
             current["grant"] == last["seal"] and current["target"] == last["target"],
             "pm-original-binding-survives-confirmed-clean-publication")

def _prefix(prefix):
    need(isinstance(prefix,str) and (prefix == "" or
         prefix.endswith("/") and not prefix.startswith("/") and
         all(part not in ("",".","..") for part in prefix[:-1].split("/"))), "pm-archive-authority-prefix")
    return prefix

def audit_transaction(files, objects, *, current_binding, raw_state, exact, euid,
                      library_path, parent, authority_prefix="authority/", journal_sha256=None,
                      profile="production-native-ack", acknowledgements=None, expected_source=None,
                      acknowledgement_prefix=None):
    """Audit one exact current B/C generation, including a shorter valid head.

    objects maps authority-relative paths to actual fstat rows (path, device,
    inode, mode, uid, links, bytes, sha256). parent is an independently captured
    directory row with its physical absolute path. files contains original raw
    bytes under authority_prefix. Returned payload bytes require an owner adapter.
    Partial head/state tails are rejected; metadata temps are retained, never used.
    """
    need(integer(euid) and euid > 0, "pm-independent-nonroot-euid")
    need(profile in ("production-native-ack","component"), "pm-explicit-transaction-profile")
    prefix = _prefix(authority_prefix)
    current = binding(current_binding)
    history = states(raw_state)
    begin,previous = _exact_begin(history,exact)
    root_id = metadata(objects["."],euid,directory=True)
    parent_id = metadata(parent,euid,directory=True,private=False)
    need(posixpath.dirname(absolute_path(library_path)) == absolute_path(parent["path"]),
         "pm-physical-library-parent-path")
    route_name = route(parent_id,library_path)
    need(current["root"] == root_id and current["parent"] == parent_id and current["route"] == route_name,
         "pm-live-binding-actual-root-parent-route")
    need(objects["."]["path"] == "." and objects[route_name]["path"] == route_name,
         "pm-root-route-fstat-paths")
    metadata(objects[route_name],euid,directory=True)
    captured = {name for name in objects if posixpath.dirname(name) == route_name}
    raw_captured = {name[len(prefix):] for name in files if name.startswith(prefix+route_name+"/")}
    need(captured == raw_captured, "pm-complete-route-raw-fstat-inventory")
    for name in captured:
        metadata(objects[name],euid)

    def original(relative):
        need(relative in objects and objects[relative]["path"] == relative, "pm-exact-fstat-map-key")
        row = objects[relative]
        need(prefix+relative in files, "pm-fstat-object-original-bytes-present")
        raw = files[prefix+relative]
        _observed(raw,posixpath.basename(relative),row,euid)
        return raw,row

    for name,pin in (("binding","identity"),("state","state"),("lease","lease")):
        raw,row = original(route_name+"/"+name)
        need(observed_id(row) == current[pin], "pm-live-binding-fstat-"+name)
        if name == "binding":
            need(raw == current_binding, "pm-observed-current-binding-bytes")
        elif name == "state":
            need(raw == raw_state, "pm-observed-current-state-bytes")

    generation,input_sha = exact["generation"],exact["input"]
    input_name = final_name(1,generation,input_sha)
    raw,row = original(route_name+"/"+input_name)
    selected = metadata_envelope(raw,input_name,row,euid)
    _origin(selected["origin"],selected["origin_raw"],current,current_binding,begin,previous,history[-1])

    hname = head_name(generation,input_sha)
    raw,row = original(route_name+"/"+hname)
    head = committed_head(raw,hname,row,euid)
    need(head["identity"] == selected["head_identity"] and head["origin_raw"] == selected["origin_raw"],
         "pm-head-independent-input-registration")

    prepared = None
    pname = final_name(2,generation,input_sha)
    if route_name+"/"+pname in objects:
        raw,row = original(route_name+"/"+pname)
        prepared = metadata_envelope(raw,pname,row,euid)
        need(prepared["pending"] == begin["seal"] and prepared["origin_raw"] == selected["origin_raw"] and
             prepared["head_identity"] == head["identity"], "pm-prepared-exact-original-b-input-head")

    slots = {}
    temporary = []
    for relative in objects:
        if posixpath.dirname(relative) != route_name:
            continue
        leaf = posixpath.basename(relative)
        if leaf.startswith("floor-"):
            match = re.fullmatch(r"floor-([0-9a-f]{16})-([0-9]{3})",leaf)
            need(match is not None, "pm-all-final-floor-names-canonical")
            g,slot = int(match[1],16),int(match[2])
            need(1 <= g <= MAX_GENERATION and 1 <= slot <= MAX_LINES and
                 leaf == f"floor-{g:016x}-{slot:03d}", "pm-final-floor-generation-slot")
            if g == generation:
                need(slot not in slots, "pm-duplicate-floor-slot")
                slots[slot] = (relative,leaf)
        elif leaf.startswith(".metadata-"):
            # Native floor enumeration ignores every non-final temp name,
            # including the preserved .metadata-uncommitted-fixture control.
            raw,row = original(relative)
            temporary.append(dict(name=leaf,bytes=len(raw),sha256=sha(raw),identity=observed_id(row)))
    largest = max(slots,default=0)
    need(set(slots) == set(range(1,largest+1)), "pm-no-immutable-floor-holes")
    need(head["count"] <= largest, "pm-committed-head-forbids-lost-final-floor")
    floor = dict(count=0,manifest=begin["manifest"],last_line_sha256=ZERO,chain_sha256=ZERO)
    floors = []
    for slot in range(1,largest+1):
        relative,leaf = slots[slot]
        raw,row = original(relative)
        envelope = metadata_envelope(raw,leaf,row,euid)
        need(envelope["input"] == input_sha and envelope["pending"] == begin["seal"] and
             envelope["origin_raw"] == selected["origin_raw"] and envelope["head_identity"] == head["identity"],
             "pm-floor-exact-original-b-input-head")
        payload = floor_payload(envelope["payload"],begin["manifest"],profile=profile)
        need(envelope["slot"] == payload["count"] == slot and payload["previous_count"] == floor["count"] and
             payload["previous_line"] == floor["last_line_sha256"] and
             payload["previous_chain"] == floor["chain_sha256"], "pm-immutable-floor-count-line-file-chain")
        floor = dict(count=slot,manifest=begin["manifest"],last_line_sha256=payload["last_line_sha256"],
                     chain_sha256=envelope["file_sha256"])
        if slot <= head["count"]:
            record = head["records"][slot-1]
            need(record["last_line_sha256"] == floor["last_line_sha256"] and
                 record["chain_sha256"] == floor["chain_sha256"], "pm-head-exact-immutable-floor-prefix")
        floors.append(dict(name=leaf,identity=envelope["identity"],file_sha256=envelope["file_sha256"],**payload))
    ack_records,ack_state = [],None
    if profile == "production-native-ack":
        need(acknowledgement_prefix is not None, "pm-explicit-actual-ack-namespace")
        ack_records,ack_state = _bind_acknowledgements(
            files,acknowledgements,euid,exact,floors,expected_source,acknowledgement_prefix)
        if history[-1]["kind"] == "C":
            need(len(ack_records) == largest == head["count"] and ack_records and
                 history[-1]["terminal"] == ack_state["last_line_sha"], "pm-clean-exact-complete-ack-floor-head")
    if journal_sha256 is not None:
        need(isinstance(journal_sha256,list) and largest <= len(journal_sha256) <= MAX_LINES and
             (not journal_sha256 or journal_sha256[0] == begin["manifest"]) and
             all(hexadecimal(value,64) and value != ZERO for value in journal_sha256),
             "pm-explicit-canonical-journal-hashes")
        need(all(row["last_line_sha256"] == journal_sha256[row["count"]-1] for row in floors),
             "pm-every-protected-floor-exact-journal-line")
        if profile == "production-native-ack":
            need(journal_sha256 == [row["line_sha256"] for row in ack_records],
                 "pm-supplied-hashes-equal-actual-ack-records")
    return dict(generation=generation,input=input_sha,manifest=begin["manifest"],begin=begin,origin=selected["origin"],
                input_record=selected,prepared_record=prepared,floors=floors,floor=floor,head=head,
                needs_head_confirm=head["count"] < largest,profile=profile,
                journal_bound=profile == "production-native-ack",acknowledgements=ack_records,
                unfloored_ack_count=len(ack_records)-largest if profile == "production-native-ack" else None,
                payload_semantics_verified=False,retained_temporary=temporary)

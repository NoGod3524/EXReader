# SPDX-License-Identifier: MIT
"""Independent PC02R001 repair ledger and original-byte qualification.

No native code is loaded. Original IDs must match independently observed source
FDs and their captured bytes, separately from each saved archive's actual ID.
The caller supplies qualified INPUT and actual SDK-image semantic validators.
"""
import posixpath
import re
import struct

from protocols import need, sha, hexadecimal, integer, json_value, ztext, history
from posix_protocols import (ZERO, u64, native_id, digest_field, sealed, metadata,
                             observed_id, absolute_path, binding, states)
from posix_migration import metadata_envelope, native_ack, floor_payload, final_name, head_name

LIMIT = 4*1024*1024
PLAN_BYTES, PART_BYTES, REF_BYTES = 5039,452,185
KINDS = {"plan":1,"applied":2,"done":3,"guard":4}
ROLES = {1:"state",2:"head",3:"binding",4:"input",5:"prepared",6:"ack",7:"floor"}


def _text(raw,offset,count,utf8=False):
    data = raw[offset:offset+count]
    need(len(data) == count and b"\0" in data, "pr-bounded-text")
    value,tail = data.split(b"\0",1)
    need(value and not any(tail), "pr-canonical-text-padding")
    return value.decode("utf-8" if utf8 else "ascii")


def _leaf(value):
    need(isinstance(value,str) and 0 < len(value) < 256 and
         re.fullmatch("[A-Za-z0-9._-]+",value) is not None and
         value not in (".","..") and not value.endswith((" ",".")), "pr-canonical-leaf")
    return value


def _sha_text(raw,offset):
    value = _text(raw,offset,65)
    need(hexadecimal(value,64) and value != ZERO, "pr-canonical-nonzero-padded-sha")
    return value


def _file(raw,offset):
    identity,size = native_id(raw,offset),u64(raw,offset+16)
    need(identity[1] > 0, "pr-nonzero-native-file-id")
    return dict(identity=identity,bytes=size,sha256=_sha_text(raw,offset+24))


def reference(raw,offset=0):
    value = raw[offset:offset+REF_BYTES]
    need(len(value) == REF_BYTES, "pr-reference185")
    if not any(value):
        return None
    info = _file(value,0)
    info.update(leaf=_leaf(_text(value,89,96)),raw=value)
    need(info["bytes"] <= LIMIT, "pr-reference-bounded-raw-file")
    return info


def repair_object(raw,row,euid,kind=None,sequence=None):
    actual = metadata(row,euid)
    need(isinstance(raw,bytes) and 177 <= len(raw) <= LIMIT and
         row["bytes"] == len(raw) and row["sha256"] == sha(raw) and
         raw[:8] == b"PC02R001", "pr-actual-wrapper112-bytes")
    k,seq,count = u64(raw,8),u64(raw,16),u64(raw,24)
    need(1 <= k <= 4 and 1 <= seq <= 256 and count == len(raw)-176 and
         count > 0 and native_id(raw,32) == actual, "pr-wrapper-kind-sequence-self-id-length")
    need(kind is None or k == kind, "pr-wrapper-exact-kind")
    need(sequence is None or seq == sequence, "pr-wrapper-exact-sequence")
    payload = raw[112:-64]
    need(digest_field(raw,48) == sha(payload) and
         digest_field(raw,len(raw)-64) == sha(raw[:-64]), "pr-wrapper-payload-and-footer-seal")
    return dict(kind=k,sequence=seq,identity=actual,bytes=len(raw),sha256=sha(raw),payload=payload,raw=raw)


def description(raw):
    need(len(raw) == 2951 and raw[2949] in (0,1) and raw[2950] in (0,1),
         "pr-sdk-description2951-flags")
    members = []
    for k in range(2):
        at = 1154+801*k
        present = raw[at+768]
        need(present in (0,1), "pr-member-original-presence")
        members.append(dict(target=_leaf(_text(raw,at,256)),
                            stage=_leaf(_text(raw,at+256,256)),
                            retained=_leaf(_text(raw,at+512,256)),
                            original_present=bool(present),
                            original=native_id(raw,at+769),prepared=native_id(raw,at+785)))
    original = []
    prepared = []
    for k in range(2):
        original.append(None if k == 1 and not raw[2949] else _file(raw,709+89*k))
        prepared.append(_file(raw,887+89*k) if raw[2950] else None)
    need(raw[2949] or not any(raw[798:887]), "pr-absent-original-mirror-zero")
    need(raw[2950] or not any(raw[887:1065]), "pr-unprepared-file-records-zero")
    return dict(raw=raw,binding=raw[:296],gates=raw[296:621],
                original_grant=raw[621:709],original=original,prepared=prepared,
                pack=_file(raw,1065),members=members,journal=_leaf(_text(raw,2756,64)),
                pack_leaf=_leaf(_text(raw,2820,64)),token=_text(raw,2884,49),
                journal_identity=native_id(raw,2933),mirror_present=bool(raw[2949]),
                has_prepared=bool(raw[2950]))


def input_description(input_record,prepared_record,library):
    """Reconstruct the owner schema directly from INPUT13844/PREPARED251."""
    raw = input_record["payload"]
    need(len(raw) == 13844 and raw[:8] == b"PC02IN01", "pr-production-input13844")
    need(_text(raw,629,4096,True) == library, "pr-input-fixed-library-route")
    partial = raw[13843]
    need(raw[13842] in (0,1) and partial in (0,1), "pr-original-input-flags")
    prepared = bytes(178)
    if prepared_record is not None:
        value = prepared_record["payload"]
        need(len(value) == 251 and value[:8] == b"PC02OUT1" and
             _sha_text(value,8) == sha(raw), "pr-production-prepared251-original-input")
        prepared = value[73:251]
    result = raw[8:304]+raw[304:629]+raw[13754:13842]+raw[13350:13528]+prepared+raw[13617:13706]
    for k in range(2):
        names = (posixpath.basename(library)+(".legacy-map.json" if k else ""),
                 _text(raw,12966+64*k,64),_text(raw,13094+64*k,64))
        for name in names:
            _leaf(name)
            encoded = name.encode("ascii")
            need(len(encoded) < 256, "pr-member-name-capacity")
            result += encoded+bytes(256-len(encoded))
        result += bytes((int(not k or bool(raw[13842])),))
        result += raw[(13350 if not k else 13439):(13366 if not k else 13455)]
        result += raw[13706+16*k:13722+16*k]
    result += raw[13222:13286]+raw[13286:13350]+raw[12917:12966]+raw[13738:13754]
    result += bytes((raw[13842],int(prepared_record is not None)))
    need(len(result) == 2951, "pr-reconstructed-sdk-description-exact-size")
    return result


def plan_payload(raw):
    need(len(raw) >= PLAN_BYTES, "pr-plan5039-minimum")
    count = u64(raw,5031)
    need(1 <= count <= 520 and len(raw) == PLAN_BYTES+count*PART_BYTES,
         "pr-plan-complete-bounded-parts452")
    sequence,first = u64(raw,0),u64(raw,8)
    need(1 <= first <= sequence <= 256, "pr-plan-sequence-first-epoch")
    d = description(raw[1003:3954])
    flags = list(raw[4222:4227])
    need(all(v in (0,1) for v in flags) and all(v in (0,1,2) for v in raw[4227:4229]),
         "pr-plan-exact-boolean-member-states")
    sk,hk,se,he = [u64(raw,at) for at in (4229,4237,4245,4253)]
    need(0 < sk <= 368*4096 and sk % 368 == 0 and
         464 <= hk <= 464+272*256 and (hk-464)%272 == 0 and
         se in (0,368) and he == 0, "pr-plan-bounded-canonical-clip-target")
    parts = []
    for index in range(count):
        at = PLAN_BYTES+index*PART_BYTES
        r = raw[at:at+PART_BYTES]
        source,saved = _file(r,0),_file(r,347)
        space,role = r[345],r[346]
        leaf,saved_leaf = _leaf(_text(r,89,256)),_leaf(_text(r,436,16))
        need(space in (1,2) and role in ROLES and
             (space == 2) == (role == 6) and saved_leaf == f"raw-{index:04d}" and
             source["bytes"] == saved["bytes"] <= LIMIT and
             source["sha256"] == saved["sha256"] and source["identity"] != saved["identity"],
             "pr-archive-part-original-saved-objects-and-canonical-name")
        parts.append(dict(index=index,space=space,role=ROLES[role],leaf=leaf,
                          saved_leaf=saved_leaf,original=source,saved=saved,raw=r))
    need(len({(p["space"],p["leaf"]) for p in parts}) == len(parts) and
         len({p["saved"]["identity"] for p in parts}) == len(parts),
         "pr-unique-original-and-saved-part-namespace")
    return dict(sequence=sequence,first=first,route_identity=native_id(raw,16),
        previous_plan=reference(raw,32),previous_done=reference(raw,217),guard=reference(raw,402),
        archive_identity=native_id(raw,587),archive_leaf=_leaf(_text(raw,603,96)),
        origin_raw=raw[699:1003],origin=binding(raw[699:1003]),description=d,
        generation=u64(raw,3954),pending=_sha_text(raw,3962),manifest=_sha_text(raw,4027),
        input=_sha_text(raw,4092),tip=_sha_text(raw,4157) if raw[4157:4222] != b"0"*64+b"\0" else ZERO,
        before_begin=bool(flags[0]),publish_intent=bool(flags[1]),committed=bool(flags[2]),
        aborted=bool(flags[3]),terminal=bool(flags[4]),member_states=list(raw[4227:4229]),
        state_keep=sk,head_keep=hk,state_extra=se,head_extra=he,
        state_record=raw[4261:4629],head_record=raw[4629:4901],
        state_target_sha256=_sha_text(raw,4901),head_target_sha256=_sha_text(raw,4966),
        parts=parts,raw=raw)


def _state_record(kind,sequence,generation,manifest,input_sha,terminal,target,previous):
    out = bytearray(368)
    out[:8] = b"PC02S001"
    out[8] = ord(kind)
    struct.pack_into("<QQ",out,16,sequence,generation)
    out[32:96] = manifest.encode()
    out[96:160] = input_sha.encode()
    out[160:224] = terminal.encode()
    struct.pack_into("<QQ",out,224,*target)
    out[240:304] = previous.encode()
    out[304:] = sha(out[:304]).encode()
    return bytes(out)


def _phase(row):
    path = row["artifact_path"]
    found = re.fullmatch(r"((?:cases|repair-cases)/[^/]+)/native-(?:authority|custody)-([^/]+)(?:/.*)?",path)
    need(found is not None, "pr-source-fstat-qualified-case-phase")
    return found[1],found[2]


class RepairAudit:
    def __init__(self,files,snapshot,source_rows,*,runtime_prefix,euid,input_decoder,image_verifier):
        self.files,self.snap,self.rows = files,snapshot,source_rows
        self.runtime,self.euid = runtime_prefix,euid
        self.prefix = runtime_prefix+snapshot["ap"]+"/"
        self.route,self.objects = snapshot["route"],snapshot["authority"]
        self.input_decoder,self.image_verifier = input_decoder,image_verifier
        self.records,self.archives,self.temporary = {},{},[]
        self.consumed = set()
        self.native_sources = []
        for row in source_rows:
            if row["directory"]:
                continue
            normalized = dict(row,mode=row["raw_mode"],path=row["source_path"])
            metadata(normalized,euid,private="/native-authority-" in row["artifact_path"])
            archive = runtime_prefix+row["artifact_path"]
            need(archive in files and row["bytes"] == len(files[archive]) and
                 row["sha256"] == sha(files[archive]), "pr-original-source-real-fstat-raw")
            self.native_sources.append(row)

    def raw(self,relative):
        return self.files[self.prefix+relative]

    def object(self,relative,kind,sequence):
        need(relative in self.objects and not self.objects[relative]["directory"],
             "pr-authoritative-repair-object-present")
        self.consumed.add(relative)
        return repair_object(self.raw(relative),self.objects[relative],self.euid,kind,sequence)

    def ref(self,ref,kind,sequence,alternatives=()):
        need(ref is not None, "pr-protected-reference-required")
        candidates = (ref["leaf"],*alternatives)
        for leaf in candidates:
            relative = self.route+"/"+leaf
            if relative not in self.objects:
                continue
            row = self.objects[relative]
            if (observed_id(row),row["bytes"],row["sha256"]) != (
                    ref["identity"],ref["bytes"],ref["sha256"]):
                continue
            return self.object(relative,kind,sequence)
        raise ValueError("pr-reference-exact-actual-id-size-and-raw-sha")

    def original_matches(self,part,raw,plan):
        parent = self.snap["authority_path"]+"/"+self.route
        if part["space"] == 2:
            parent = posixpath.dirname(self.snap["library"])+"/"+plan["description"]["journal"]
        path = parent+"/"+part["leaf"]
        info = part["original"]
        matches = []
        for row in self.native_sources:
            if row["source_path"] == path and observed_id(row) == info["identity"] and \
               row["bytes"] == info["bytes"] and row["sha256"] == info["sha256"]:
                need(self.files[self.runtime+row["artifact_path"]] == raw,
                     "pr-independent-original-source-bytes-equal-saved-copy")
                matches.append(row)
        need(matches, "pr-original-id-not-inferred-from-plan-or-binding")
        return matches

    def saved_parts(self,plan):
        archive = self.route+"/"+plan["archive_leaf"]
        need(archive in self.objects and self.objects[archive]["directory"] and
             metadata(self.objects[archive],self.euid,directory=True) == plan["archive_identity"],
             "pr-archive-actual-private-directory-id")
        match = re.fullmatch(r"repair-archive-([0-9]{6})-([1-9][0-9]*)-([0-9]+)",plan["archive_leaf"])
        need(match is not None and int(match[1]) == plan["sequence"] and
             0 < int(match[2]) < 2**31 and 0 <= int(match[3]) < 1024,
             "pr-archive-canonical-sequence-pid-serial")
        self.consumed.add(archive)
        sources = {}
        phases = None
        for part in plan["parts"]:
            path = archive+"/"+part["saved_leaf"]
            need(path in self.objects and not self.objects[path]["directory"],
                 "pr-saved-original-present")
            row,raw = self.objects[path],self.raw(path)
            info = part["saved"]
            need(metadata(row,self.euid) == info["identity"] and row["bytes"] == info["bytes"] == len(raw) and
                 row["sha256"] == info["sha256"] == sha(raw), "pr-actual-saved-fd-id-size-bytes-sha")
            originals = self.original_matches(part,raw,plan)
            eligible = {_phase(r) for r in originals}
            phases = eligible if phases is None else phases & eligible
            sources[part["role"],part["leaf"]] = dict(part=part,raw=raw,observed=originals)
            self.consumed.add(path)
        need(phases, "pr-all-original-parts-share-real-preapply-source-snapshot")
        plan["original_phases"] = sorted(phases)
        plan["saved_sources"] = sources
        return sources

    @staticmethod
    def only(sources,role):
        found = [value for (key,_),value in sources.items() if key == role]
        need(len(found) == 1, "pr-exact-one-original-role:"+role)
        return found[0]

    def observed(self,source,phases):
        found = [r for r in source["observed"] if _phase(r) in phases]
        need(found, "pr-original-real-fd-in-consistent-phase")
        row = found[0]
        return dict(row,path=source["part"]["leaf"],mode=row["raw_mode"])

    def plan_semantics(self,plan):
        sources = self.saved_parts(plan)
        state,head,original_binding,input_source = [self.only(sources,r) for r in ("state","head","binding","input")]
        need(state["part"]["leaf"] == "state" and original_binding["part"]["leaf"] == "binding",
             "pr-exact-state-binding-original-names")
        generation = plan["generation"]
        need(1 <= generation <= 2047 and plan["origin"]["generation"] == generation-1 and
             plan["origin"]["identity"][1] > 0, "pr-original-generation-bound")
        inp_name = final_name(1,generation,plan["input"])
        need(input_source["part"]["leaf"] == inp_name, "pr-exact-input-metadata-name")
        inp_record = metadata_envelope(input_source["raw"],inp_name,
                      self.observed(input_source,plan["original_phases"]),self.euid)
        need(inp_record["origin_raw"] == plan["origin_raw"] and inp_record["input"] == plan["input"] and
             inp_record["generation"] == generation, "pr-plan-original-input-and-binding")
        prepared_sources = [v for (r,_),v in sources.items() if r == "prepared"]
        need(len(prepared_sources) == int(plan["description"]["has_prepared"]),
             "pr-exact-optional-prepared-original")
        prepared_record = None
        if prepared_sources:
            item = prepared_sources[0]
            name = final_name(2,generation,plan["input"])
            need(item["part"]["leaf"] == name, "pr-exact-prepared-metadata-name")
            prepared_record = metadata_envelope(item["raw"],name,
                        self.observed(item,plan["original_phases"]),self.euid)
            need(prepared_record["origin_raw"] == plan["origin_raw"] and
                 prepared_record["pending"] == plan["pending"] and
                 prepared_record["head_identity"] == inp_record["head_identity"],
                 "pr-prepared-exact-original-b-head")
        need(input_description(inp_record,prepared_record,self.snap["library"]) ==
             plan["description"]["raw"], "pr-schema2951-derived-from-production-input-prepared")
        need(callable(self.input_decoder), "pr-qualified-owner-input-semantic-decoder-required")
        decoded_input = self.input_decoder(inp_record)
        need(decoded_input["manifest_sha256"] == plan["manifest"] and
             decoded_input["sha256"] == plan["input"], "pr-input-owner-actual-manifest-and-payload")
        origin = plan["origin"]
        need(observed_id(self.objects["."]) == origin["root"] and
             observed_id(self.objects[self.route]) == plan["route_identity"] and
             origin["route"] == self.route and origin["parent"] == observed_id(self.snap["parent"]),
             "pr-plan-pinned-native-authority-route-parent")
        original_b = binding(original_binding["raw"])
        need(original_b["identity"] == original_binding["part"]["original"]["identity"],
             "pr-original-binding-actual-self-id")
        for key in ("root","parent","lease","state","route"):
            need(original_b[key] == origin[key], "pr-original-binding-pinned-"+key)
        need(state["part"]["original"]["identity"] == origin["state"] and
             head["part"]["original"]["identity"] == inp_record["head_identity"],
             "pr-original-state-and-registered-head-actual-ids")
        sk = len(state["raw"])//368*368
        need(sk > 0 and len(state["raw"]) <= 368*4096, "pr-whole-state-bound-including-tail")
        state_history = states(state["raw"][:sk])
        tail = state["raw"][sk:]
        previous = state_history[-1]
        begin = _state_record("B",generation*2,generation,plan["manifest"],plan["input"],ZERO,
                              origin["target"],origin["grant"])
        need(sha(begin[:304]) == plan["pending"], "pr-canonical-original-b-exact-seal")
        if plan["before_begin"]:
            need(tail and previous["kind"] in ("I","C") and previous["generation"] == generation-1 and
                 previous["seal"] == origin["grant"] and previous["target"] == origin["target"] and
                 plan["origin_raw"] == original_binding["raw"] and begin.startswith(tail),
                 "pr-partial-b-exact-next-record-after-existing-clean-grant")
        else:
            need(len(state_history) >= generation*2 and
                 state["raw"][(generation*2-1)*368:generation*2*368] == begin,
                 "pr-original-full-b-not-reconstructed-as-authority")
        journal,ack_records,floors,head_info = self.transaction_prefix(plan,sources,inp_record,head,decoded_input)
        need(plan["tip"] == (journal.get("last_line_sha",ZERO)) and
             all(plan[k] == journal[k] for k in ("publish_intent","committed","aborted")) and
             plan["terminal"] == (journal["event"] == 12), "pr-plan-flags-from-real-complete-ack-history")
        if plan["before_begin"]:
            need(not ack_records and not floors and not head_info["count"] and not head_info["tail"] and
                 not plan["state_extra"], "pr-before-begin-never-creates-live-pending")
            canonical_c = bytes(368)
        elif tail:
            need(previous["kind"] == "B" and journal["event"] == 12 and
                 journal["committed"] != journal["aborted"] and not head_info["tail"] and
                 len(ack_records) == len(floors) == head_info["count"],
                 "pr-partial-c-exact-terminal-full-protected-prefix")
            target = (plan["description"]["prepared"][0] if journal["committed"] else
                      plan["description"]["original"][0])["identity"]
            canonical_c = _state_record("C",len(state_history)+1,generation,plan["manifest"],plan["input"],
                                        journal["last_line_sha"],target,plan["pending"])
            need(canonical_c.startswith(tail) and plan["state_record"] == canonical_c,
                 "pr-partial-c-matches-unique-independent-terminal-record")
            if original_b["generation"] == generation:
                need(plan["state_extra"] == 368 and original_b["grant"] == canonical_c[304:].decode() and
                     original_b["target"] == target, "pr-binding-selected-c-never-rolled-back-to-b")
            else:
                need(original_b["generation"] == generation-1 and plan["state_extra"] == 0 and
                     original_binding["raw"] == plan["origin_raw"], "pr-unpublished-c-requires-fresh-finish")
        else:
            canonical_c = bytes(368)
            need(not plan["state_extra"] and head_info["tail"] and previous["kind"] == "B",
                 "pr-complete-state-not-discarded-as-an-interrupted-tail")
        need(plan["state_keep"] == sk and plan["head_keep"] == head_info["keep"] and
             not (tail and head_info["tail"]), "pr-single-interrupted-state-or-head-only")
        if not tail or plan["before_begin"]:
            need(plan["state_record"] == bytes(368), "pr-no-invented-canonical-state-record")
        if head_info["tail"]:
            need(plan["head_record"] == head_info["next"], "pr-exact-next-head-record-for-unacknowledged-tail")
        else:
            need(plan["head_record"] == bytes(272), "pr-no-head-record-without-partial-tail")
        state_target = state["raw"][:sk]+(canonical_c if plan["state_extra"] else b"")
        need(sha(state_target) == plan["state_target_sha256"] and
             sha(head["raw"][:head_info["keep"]]) == plan["head_target_sha256"],
             "pr-independently-derived-exact-application-target-bytes")
        need(callable(self.image_verifier), "pr-independent-actual-source-sdk-images-required")
        images = self.image_verifier(plan,decoded_input,plan["original_phases"])
        need(isinstance(images,dict) and images.get("verified") is True,
             "pr-actual-original-prepared-images-semantic-proof")
        plan.update(input_record=inp_record,prepared_record=prepared_record,input_decoded=decoded_input,
                    state_source=state,head_source=head,ack_records=ack_records,floors=floors,
                    journal=journal,head_info=head_info,state_target=state_target,images=images)
        return plan

    def transaction_prefix(self,plan,sources,inp,head,decoded):
        acks = sorted([v for (role,_),v in sources.items() if role == "ack"],
                      key=lambda v:v["part"]["leaf"])
        floor_sources = sorted([v for (role,_),v in sources.items() if role == "floor"],
                               key=lambda v:v["part"]["leaf"])
        need(len(acks) <= 256 and len(floor_sources) <= 256, "pr-original-prefix-bounded")
        expected_parts = [("state","state"),("head",head_name(plan["generation"],plan["input"])),
                          ("binding","binding"),("input",final_name(1,plan["generation"],plan["input"]))]
        if plan["description"]["has_prepared"]:
            expected_parts.append(("prepared",final_name(2,plan["generation"],plan["input"])))
        expected_parts += [("ack",f"ack-{k:03d}") for k in range(1,len(acks)+1)]
        expected_parts += [("floor",final_name(3,plan["generation"],plan["input"],k))
                           for k in range(1,len(floor_sources)+1)]
        need([(p["role"],p["leaf"]) for p in plan["parts"]] == expected_parts,
             "pr-complete-exact-ordered-original-inventory")
        ack_records = []
        for index,item in enumerate(acks,1):
            name = f"ack-{index:03d}"
            need(item["part"]["leaf"] == name, "pr-original-ack-no-holes")
            record = native_ack(item["raw"],name,self.observed(item,plan["original_phases"]),self.euid)
            need(record["manifest"] == plan["manifest"] and record["input"] == plan["input"] and
                 record["pending"] == plan["pending"], "pr-original-ack-exact-transaction")
            ack_records.append(record)
        lines = [r["line"] for r in ack_records]
        journal = history(lines,decoded["binding"]["source"])
        if lines:
            need(lines[0] == decoded["manifest"], "pr-original-ack-qualified-manifest")
            need(journal["lease"] in ("-",decoded["token"]) and journal["stage"] in ("-",decoded["token"]),
                 "pr-original-journal-owner-native-token")
            if journal["snapshot"] != "-":
                need(journal["snapshot"] == decoded["snapshot_sha256"], "pr-original-journal-native-source-snapshot")
            if journal["content"] != "-":
                need(journal["content"] == decoded["content_sha256"], "pr-original-journal-original-content-digest")
        need(len(floor_sources) <= len(ack_records) <= len(floor_sources)+1,
             "pr-at-most-one-final-ack-before-protected-floor")
        floors = []
        previous_line = previous_floor = ZERO
        for index,item in enumerate(floor_sources,1):
            name = final_name(3,plan["generation"],plan["input"],index)
            need(item["part"]["leaf"] == name, "pr-original-floors-no-holes")
            record = metadata_envelope(item["raw"],name,
                       self.observed(item,plan["original_phases"]),self.euid)
            need(record["phase"] == 3 and record["origin_raw"] == plan["origin_raw"] and
                 record["pending"] == plan["pending"] and record["input"] == plan["input"] and
                 record["head_identity"] == inp["head_identity"], "pr-floor-envelope-exact-original-registration")
            value = floor_payload(record["payload"],plan["manifest"],profile="production-native-ack")
            ack = ack_records[index-1]
            need(value["previous_count"] == index-1 and value["count"] == index and
                 value["previous_line"] == previous_line and value["previous_chain"] == previous_floor and
                 value["last_line_sha256"] == ack["line_sha256"] and
                 value["ack_identity"] == ack["identity"] and value["ack_sha256"] == ack["file_sha256"],
                 "pr-every-original-floor352-real-ack-fstat-and-whole-raw")
            previous_line,previous_floor = ack["line_sha256"],sha(item["raw"])
            floors.append(dict(**value,file_sha256=sha(item["raw"]),identity=record["identity"]))
        raw = head["raw"]
        need(464 <= len(raw) <= 464+256*272, "pr-original-head-bounded")
        sealed(raw[:464],b"PC02F001",400)
        need(u64(raw,8) == plan["generation"] and digest_field(raw,16) == plan["input"] and
             raw[80:384] == plan["origin_raw"] and native_id(raw,384) ==
             head["part"]["original"]["identity"] == inp["head_identity"],
             "pr-original-head-actual-self-id-and-input-origin")
        complete = (len(raw)-464)//272
        keep = 464+complete*272
        tail = raw[keep:]
        need(complete <= len(floors) <= complete+1 and
             (not (complete < len(floors) or tail) or len(acks) == len(floors)) and
             (not tail or complete < len(floors)), "pr-single-interrupted-head-floor-ack-combination")
        previous = raw[400:464]
        next_record = bytes(272)
        for index in range(len(floors)):
            record = bytearray(272)
            record[:8] = b"PC02H001"
            struct.pack_into("<Q",record,8,index+1)
            record[16:80] = floors[index]["last_line_sha256"].encode()
            record[80:144] = floors[index]["file_sha256"].encode()
            record[144:208] = previous
            record[208:272] = sha(record[:208]).encode()
            if index < complete:
                need(raw[464+index*272:464+(index+1)*272] == bytes(record),
                     "pr-complete-head-record-never-discarded-or-normalized")
                previous = bytes(record[208:272])
            else:
                next_record = bytes(record)
        need(not tail or next_record.startswith(tail), "pr-original-partial-head-exact-unique-next-record")
        return journal,ack_records,floors,dict(count=complete,keep=keep,tail=tail,next=next_record)

    def minimum(self,plan,applied):
        raw = applied["payload"]
        need(len(raw) == 363, "pr-applied363")
        selected = reference(raw,0)
        need(selected is not None and selected["raw"] == plan["reference"]["raw"],
             "pr-applied-exact-immutable-plan-reference")
        state,head = plan["state_source"],plan["head_source"]
        state_id,head_id = native_id(raw,185),native_id(raw,209)
        state_size,head_size = u64(raw,201),u64(raw,225)
        state_sha,head_sha = _sha_text(raw,233),_sha_text(raw,298)
        need(state_id == state["part"]["original"]["identity"] and
             head_id == head["part"]["original"]["identity"] and
             state_size == plan["state_keep"]+plan["state_extra"] and
             head_size == plan["head_keep"] and state_sha == plan["state_target_sha256"] and
             head_sha == plan["head_target_sha256"], "pr-applied-exact-plan-derived-targets")
        self.prefix_minimum(self.route+"/state",state_id,state_size,state_sha,"state")
        self.prefix_minimum(self.route+"/"+head["part"]["leaf"],head_id,head_size,head_sha,"head")
        return dict(state_identity=state_id,state_bytes=state_size,state_sha256=state_sha,
                    head_identity=head_id,head_bytes=head_size,head_sha256=head_sha)

    def prefix_minimum(self,path,identity,count,digest,role):
        need(path in self.objects and not self.objects[path]["directory"] and
             observed_id(self.objects[path]) == identity, "pr-protected-"+role+"-actual-native-id")
        raw = self.raw(path)
        need(0 <= count <= len(raw) and sha(raw[:count]) == digest,
             "pr-applied-"+role+"-protected-minimum")
        return raw[:count]

    def unfinished_source(self,plan):
        for source,keep,extra,target in (
                (plan["state_source"],plan["state_keep"],plan["state_extra"],plan["state_target"]),
                (plan["head_source"],plan["head_keep"],0,plan["head_source"]["raw"][:plan["head_keep"]])):
            path = self.route+"/"+source["part"]["leaf"]
            need(path in self.objects and observed_id(self.objects[path]) ==
                 source["part"]["original"]["identity"], "pr-unapplied-source-native-id")
            now = self.raw(path)
            maximum = max(len(source["raw"]),len(target))
            need(keep <= len(now) <= maximum and
                 (target.startswith(now) if extra else source["raw"].startswith(now)),
                 "pr-unapplied-source-only-original-or-exact-target-prefix")
        b = self.only(plan["saved_sources"],"binding")
        need(self.raw(self.route+"/binding") == b["raw"] and observed_id(self.objects[self.route+"/binding"]) ==
             b["part"]["original"]["identity"], "pr-no-new-binding-before-applied")

    def done(self,plan,record,previous_done,guard,applied_ref):
        raw = record["payload"]
        need(len(raw) == 1254 and u64(raw,0) == plan["first"] and
             u64(raw,8) == plan["sequence"] and native_id(raw,16) == plan["route_identity"],
             "pr-done1254-exact-epoch-route")
        refs = [reference(raw,at) for at in (32,217,402,587)]
        need(refs[0] is not None and refs[0]["raw"] == guard["raw"] and
             refs[1] is not None and refs[1]["raw"] == plan["reference"]["raw"] and
             refs[2] is not None and refs[2]["raw"] == applied_ref["raw"] and
             (refs[3]["raw"] if refs[3] else None) ==
             (previous_done["raw"] if previous_done else None), "pr-done-exact-protected-reference-chain")
        raw_binding = raw[772:1076]
        final = binding(raw_binding)
        state_id,head_id = native_id(raw,1076),native_id(raw,1100)
        state_size,head_size = u64(raw,1092),u64(raw,1116)
        state_sha,head_sha = _sha_text(raw,1124),_sha_text(raw,1189)
        need(state_id == plan["state_source"]["part"]["original"]["identity"] and
             head_id == plan["head_source"]["part"]["original"]["identity"],
             "pr-done-actual-original-state-head-identities")
        complete_state = self.prefix_minimum(self.route+"/state",state_id,state_size,state_sha,"state")
        complete_head = self.prefix_minimum(self.route+"/"+plan["head_source"]["part"]["leaf"],
                                           head_id,head_size,head_sha,"head")
        recorded = states(complete_state)
        need((len(complete_head)-464)%272 == 0 and len(complete_head) >= plan["head_keep"],
             "pr-done-complete-head-preserves-applied-prefix")
        need(any(r["source_path"] == self.snap["authority_path"]+"/"+self.route+"/binding" and
                 observed_id(r) == final["identity"] and r["bytes"] == 304 and
                 r["sha256"] == sha(raw_binding) and self.files[self.runtime+r["artifact_path"]] == raw_binding
                 for r in self.native_sources), "pr-done-binding-real-fstat-not-embedded-self-id-only")
        if plan["before_begin"]:
            need(raw_binding == plan["origin_raw"] and state_size == plan["state_keep"] and
                 complete_state == plan["state_source"]["raw"][:plan["state_keep"]],
                 "pr-before-begin-restores-only-same-existing-grant")
        else:
            terminal = recorded[-1]
            need(terminal["kind"] == "C" and terminal["generation"] == final["generation"] == plan["generation"] and
                 terminal["input"] == plan["input"] and terminal["manifest"] == plan["manifest"] and
                 terminal["seal"] == final["grant"] and terminal["target"] == final["target"],
                 "pr-done-complete-c-exact-binding-terminal")
            # Full final transaction validation is supplied by the owner adapter
            # from actual live ACK/floor/head namespaces, not this old prefix.
        current = binding(self.snap["binding_raw"])
        need(current["generation"] >= final["generation"] and
             (current["generation"] != final["generation"] or self.snap["binding_raw"] == raw_binding),
             "pr-done-historical-complete-grant-never-replaced-by-older")
        terminal_namespace = _done_namespace(self,plan,complete_state,complete_head)
        return dict(binding=final,binding_raw=raw_binding,state_bytes=state_size,head_bytes=head_size,
                    state_sha256=state_sha,head_sha256=head_sha,terminal_namespace=terminal_namespace)

    def inventory(self,referenced_archives):
        """Account every repair object, including unadopted failure evidence."""
        direct = self.route+"/"
        orphans = []
        for name,row in self.objects.items():
            if not name.startswith(direct):
                continue
            relative = name[len(direct):]
            leaf = posixpath.basename(name)
            if not relative.startswith(("repair-","repair.")):
                continue
            if name in self.consumed:
                continue
            parts = relative.split("/")
            if len(parts) == 1 and re.fullmatch(r"repair-next-[1-9][0-9]*-(?:0|[1-9][0-9]*)",leaf):
                need(not row["directory"] and int(leaf.rsplit("-",1)[1]) < 1024 and
                     row["bytes"] <= LIMIT, "pr-retained-storage-temp-bounded")
                self.temporary.append(dict(path=name,identity=observed_id(row),bytes=row["bytes"],sha256=row["sha256"]))
            elif len(parts) == 1 and re.fullmatch(r"repair-archive-[0-9]{6}-[1-9][0-9]*-(?:0|[1-9][0-9]*)",leaf):
                need(row["directory"], "pr-orphan-archive-is-private-directory")
                metadata(row,self.euid,directory=True)
                archive_name = re.fullmatch(r"repair-archive-([0-9]{6})-([1-9][0-9]*)-([0-9]+)",leaf)
                need(archive_name is not None and 1 <= int(archive_name[1]) <= self.plan_count+1 and
                     int(archive_name[2]) < 2**31 and int(archive_name[3]) < 1024,
                     "pr-unreferenced-archive-canonical-next-sequence")
                orphans.append(name)
            elif len(parts) == 2 and parts[0].startswith("repair-archive-"):
                need(not row["directory"], "pr-repair-archive-has-no-unknown-subdirectory")
                if re.fullmatch(r"raw-[0-9]{4}",leaf):
                    need(self.route+"/"+parts[0] not in referenced_archives and int(leaf[4:]) < 520,
                         "pr-no-extra-final-raw-in-protected-archive")
                elif re.fullmatch(r"repair-next-[1-9][0-9]*-(?:0|[1-9][0-9]*)",leaf):
                    need(int(leaf.rsplit("-",1)[1]) < 1024 and row["bytes"] <= LIMIT,
                         "pr-retained-archive-storage-temp-bounded")
                    self.temporary.append(dict(path=name,identity=observed_id(row),bytes=row["bytes"],sha256=row["sha256"]))
                else:
                    match = re.fullmatch(r"proof-([1-9][0-9]*)-([0-3])-((?:0|[1-9][0-9]*))\.image(?:-(wal|shm|journal))?",leaf)
                    need(match is not None and int(match[1]) < 2**31 and int(match[3]) < 1024,
                         "pr-only-qualified-sdk-proof-factory-files")
                    if match[4]:
                        base = name.rsplit("-",1)[0]
                        need(base in self.objects, "pr-proof-sidecar-retains-own-image")
                    # The owner image callback must consume valid proof images
                    # and explicitly retain failed ones/sidecars as non-authority.
                    need(name in self.proof_accounted, "pr-every-sdk-proof-image-independently-accounted")
            else:
                raise ValueError("pr-unknown-or-extra-repair-object")
            self.consumed.add(name)
        for archive in orphans:
            names = sorted(posixpath.basename(path) for path in self.objects
                           if posixpath.dirname(path) == archive and
                           posixpath.basename(path).startswith("raw-"))
            need(names == [f"raw-{k:04d}" for k in range(len(names))],
                 "pr-unreferenced-archive-complete-raw-prefix-no-holes")
        return orphans

    def run(self):
        rn = self.route+"/"
        bykind = {1:{},2:{},3:{}}
        guards = {}
        for path,row in self.objects.items():
            if posixpath.dirname(path) != self.route:
                continue
            leaf = posixpath.basename(path)
            match = re.fullmatch(r"repair-(plan|applied|done)-([0-9]{6})",leaf)
            if match:
                kind,number = KINDS[match[1]],int(match[2])
                need(1 <= number <= 256 and number not in bykind[kind], "pr-canonical-unique-record-sequence")
                bykind[kind][number] = self.object(path,kind,number)
            elif leaf == "repair.guard":
                record = self.object(path,4,None)
                guards["active"] = record
            elif re.fullmatch(r"repair-guard-[0-9]{6}\.retired",leaf):
                number = int(leaf[13:19])
                need(1 <= number <= 256 and number not in guards, "pr-retired-guard-canonical-first")
                guards[number] = self.object(path,4,number)
        plans,applied,done = bykind[1],bykind[2],bykind[3]
        self.plan_count = len(plans)
        need(set(plans) == set(range(1,len(plans)+1)), "pr-no-missing-complete-plan-in-global-chain")
        need(set(applied) <= set(plans) and set(done) <= set(plans), "pr-no-orphan-applied-or-done-marker")
        self.proof_accounted = set()
        previous_plan = previous_done = epoch_guard = None
        first = None
        closed = True
        qualified = []
        referenced_archives = set()
        used_guards = set()
        for sequence in range(1,len(plans)+1):
            record = plans[sequence]
            plan = plan_payload(record["payload"])
            need(plan["sequence"] == sequence and plan["guard"] is not None,
                 "pr-plan-wrapper-payload-exact-sequence-and-guard")
            plan["reference"] = dict(identity=record["identity"],bytes=record["bytes"],sha256=record["sha256"],
                                     leaf=f"repair-plan-{sequence:06d}")
            plan["reference"]["raw"] = (struct.pack("<QQQ",*record["identity"],record["bytes"])+
                                       record["sha256"].encode()+b"\0"+
                                       plan["reference"]["leaf"].encode()+
                                       bytes(96-len(plan["reference"]["leaf"])))
            need(len(plan["reference"]["raw"]) == 185, "pr-exact-current-plan-reference-wire")
            need((plan["previous_plan"]["raw"] if plan["previous_plan"] else None) ==
                 (previous_plan["raw"] if previous_plan else None) and
                 (plan["previous_done"]["raw"] if plan["previous_done"] else None) ==
                 (previous_done["raw"] if previous_done else None), "pr-global-plan-and-closed-epoch-chain")
            if closed:
                first = sequence
                need(plan["first"] == sequence and plan["guard"]["leaf"] == "repair.guard",
                     "pr-new-epoch-exact-first-and-fixed-guard")
                epoch_guard = plan["guard"]
                actual_guard = self.ref(epoch_guard,4,first,(f"repair-guard-{first:06d}.retired",))
                expected = bytearray(record["payload"])
                expected[402:587] = bytes(185)
                need(actual_guard["payload"] == bytes(expected), "pr-guard-original-proposal-before-plan-with-reference")
                used_guards.add(actual_guard["identity"])
                closed = False
            else:
                need(plan["first"] == first and plan["guard"]["raw"] == epoch_guard["raw"],
                     "pr-active-epoch-original-guard-preserved")
            self.plan_semantics(plan)
            referenced_archives.add(self.route+"/"+plan["archive_leaf"])
            self.proof_accounted.update(plan["images"].get("accounted",[]))
            ap = applied.get(sequence)
            ap_ref = None
            if ap is not None:
                ap_ref = self.record_reference(ap,f"repair-applied-{sequence:06d}")
                plan["applied"] = self.minimum(plan,ap)
            else:
                need(sequence == len(plans) and sequence not in done, "pr-every-complete-prior-plan-has-original-applied")
                self.unfinished_source(plan)
                plan["applied"] = None
            if sequence in done:
                need(ap is not None, "pr-done-only-after-original-applied")
                plan["done"] = self.done(plan,done[sequence],previous_done,epoch_guard,ap_ref)
                previous_done = self.record_reference(done[sequence],f"repair-done-{sequence:06d}")
                closed = True
            else:
                plan["done"] = None
            previous_plan = plan["reference"]
            qualified.append(plan)
        active = guards.get("active")
        orphan_guard = None
        if active is not None and active["identity"] not in used_guards:
            sequence = len(plans)+1
            need(active["sequence"] == sequence and closed and sequence <= 256,
                 "pr-uncommitted-guard-next-sequence-only")
            orphan_guard = plan_payload(active["payload"])
            need(orphan_guard["sequence"] == orphan_guard["first"] == sequence and
                 orphan_guard["guard"] is None and
                 (orphan_guard["previous_plan"]["raw"] if orphan_guard["previous_plan"] else None) ==
                 (previous_plan["raw"] if previous_plan else None) and
                 (orphan_guard["previous_done"]["raw"] if orphan_guard["previous_done"] else None) ==
                 (previous_done["raw"] if previous_done else None),
                 "pr-orphan-guard-is-full-original-next-proposal")
            self.plan_semantics(orphan_guard)
            self.proof_accounted.update(orphan_guard["images"].get("accounted",[]))
            self.unfinished_source(orphan_guard)
            for source in (orphan_guard["state_source"],orphan_guard["head_source"]):
                need(self.raw(self.route+"/"+source["part"]["leaf"]) == source["raw"],
                     "pr-orphan-guard-precedes-all-source-mutation")
            referenced_archives.add(self.route+"/"+orphan_guard["archive_leaf"])
            used_guards.add(active["identity"])
        if qualified and not closed:
            need(active is not None and active["identity"] == epoch_guard["identity"],
                 "pr-active-epoch-never-loses-fixed-guard")
        for key,guard in guards.items():
            need(guard["identity"] in used_guards, "pr-no-unreferenced-complete-guard")
            if key != "active":
                need(any(p["first"] == key and p["done"] is not None for p in qualified),
                     "pr-guard-retirement-only-after-actual-done")
        orphans = self.inventory(referenced_archives)
        return dict(plans=qualified,epochs=len({p["first"] for p in qualified}),
                    applied=len(applied),done=len(done),active=active is not None,unfinished_epoch=bool(qualified and not closed),
                    orphan_guard=orphan_guard,orphan_archives=orphans,retained_temporary=self.temporary,
                    consumed=self.consumed,verified=True)

    @staticmethod
    def record_reference(record,leaf):
        raw = struct.pack("<QQQ",*record["identity"],record["bytes"])+record["sha256"].encode()+b"\0"
        raw += leaf.encode()+bytes(96-len(leaf))
        need(len(raw) == 185, "pr-marker-reference185")
        return dict(identity=record["identity"],bytes=record["bytes"],sha256=record["sha256"],leaf=leaf,raw=raw)


def audit_repair_history(files,snapshot,source_rows,*,runtime_prefix,euid,input_decoder,image_verifier):
    return RepairAudit(files,snapshot,source_rows,runtime_prefix=runtime_prefix,euid=euid,
                       input_decoder=input_decoder,image_verifier=image_verifier).run()


def _done_namespace(audit,plan,complete_state,complete_head):
    """DONE protects the final complete namespace, beyond PLAN's old prefix."""
    snap,rn = audit.snap,audit.route
    journal = plan["description"]["journal"]
    actual_acks = sorted(path for path,row in snap["custody"].items()
                         if posixpath.dirname(path) == journal and
                         posixpath.basename(path).startswith("ack-"))
    count = (len(complete_head)-464)//272
    if plan["before_begin"]:
        head_path = rn+"/"+head_name(plan["generation"],plan["input"])
        need(count == 0 and not actual_acks and len(complete_head) == 464 and
             audit.raw(head_path) == complete_head,
             "pr-done-before-begin-own-journal-empty-and-original-head-only")
        return dict(ack_count=0,floor_count=0,head_count=0,terminal_guard=True,before_begin=True)
    need(actual_acks == [journal+f"/ack-{k:03d}" for k in range(1,count+1)],
         "pr-done-complete-ack-inventory")
    expected_floors = [rn+"/"+final_name(3,plan["generation"],plan["input"],k)
                       for k in range(1,count+1)]
    floor_prefix = rn+f"/floor-{plan['generation']:016x}-"
    actual_floors = sorted(path for path in audit.objects if path.startswith(floor_prefix))
    need(actual_floors == expected_floors, "pr-done-complete-floor-inventory")
    head_path = rn+"/"+head_name(plan["generation"],plan["input"])
    need(audit.raw(head_path) == complete_head, "pr-done-final-head-eof-never-extended-or-trimmed")
    sources = {key:value for key,value in plan["saved_sources"].items()
               if key[0] not in ("ack","floor","head")}
    phases = set()

    def current(role,name,row,raw):
        path = row["artifact_path"]
        found = [r for r in audit.native_sources if r["artifact_path"] == path]
        need(len(found) == 1, "pr-done-current-object-real-fstat")
        phases.add(_phase(found[0]))
        info = dict(identity=observed_id(row),bytes=row["bytes"],sha256=row["sha256"])
        return dict(part=dict(role=role,leaf=name,original=info),raw=raw,observed=found)

    head = current("head",posixpath.basename(head_path),audit.objects[head_path],audit.raw(head_path))
    sources["head",head["part"]["leaf"]] = head
    for path in actual_acks:
        name = posixpath.basename(path)
        row = snap["custody"][path]
        sources["ack",name] = current("ack",name,row,
                                      audit.files[audit.runtime+snap["cp"]+"/"+path])
    for path in actual_floors:
        name = posixpath.basename(path)
        sources["floor",name] = current("floor",name,audit.objects[path],audit.raw(path))
    need(len(phases) == 1, "pr-done-complete-prefix-from-one-actual-current-snapshot")
    view = dict(plan,original_phases=list(phases))
    view["parts"] = [p for p in plan["parts"] if p["role"] not in ("ack","floor")]
    view["parts"] += [sources["ack",f"ack-{k:03d}"]["part"] for k in range(1,count+1)]
    view["parts"] += [sources["floor",posixpath.basename(path)]["part"] for path in actual_floors]
    state,acks,floors,head_info = audit.transaction_prefix(
        view,sources,plan["input_record"],head,plan["input_decoded"])
    need(not head_info["tail"] and head_info["count"] == len(acks) == len(floors) == count,
         "pr-done-final-ack-floor-head-exact-complete-count")
    if plan["before_begin"]:
        need(count == 0, "pr-done-before-begin-has-no-authoritative-ack")
    else:
        complete = states(complete_state)[-1]
        need(state["event"] == 12 and state["committed"] != state["aborted"] and
             state["last_line_sha"] == complete["terminal"] and
             complete["kind"] == "C" and complete["generation"] == plan["generation"] and
             complete["input"] == plan["input"] and complete["manifest"] == plan["manifest"],
             "pr-done-final-release-and-native-clean-terminal")
    return dict(ack_count=count,floor_count=count,head_count=count,terminal_guard=True)

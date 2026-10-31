# SPDX-License-Identifier: MIT
"""Production C02 capsule, candidate-record and explicit repair audit."""
import struct

from protocols import (need, sha, hexadecimal, ztext, native_file, registry_binding,
                       gate_records, history, native_pair, MANIFEST_KEYS)

def manifest_line(packet):
    fields = {**packet["binding"],**dict(zip(
        ("admission","publisher","recovery","observer","fault"),packet["gates"]))}
    return ("EXRWH2|"+"|".join(key+"="+fields[key] for key in MANIFEST_KEYS)).encode()

def input_digests(packet):
    binding = packet["binding"]
    text = "EXRWC-BIND1\n"+"".join(
        key+"="+binding[key]+"\n" for key in ("source","run","attempt","artifact","platform","sdk","provider"))
    bind = sha(text.encode())
    records = [(packet["original"],"library.sqlite")]
    if packet["mirror"] is not None:
        records.append((packet["mirror"],"mirror.json"))
    records.append((packet["pack_file"],"pack.exrpack"))
    snapshot = f"EXRWC-SNAP1 {bind} {len(records)}\n"
    content = f"EXRWC-CONTENT1 {len(records)}\n"
    for row,path in records:
        tail = f"f {row['size']} {row['sha256']} {path}\n"
        snapshot += row["identity"].hex()+" "+tail
        content += tail
    return sha(snapshot.encode()),sha(content.encode())

def bound_history(lines,packet):
    result = history(lines,packet["binding"]["source"])
    if not lines:
        return result
    need(lines[0] == manifest_line(packet), "production-exact-manifest")
    snapshot,content = input_digests(packet)
    need(result["snapshot"] in ("-",snapshot) and result["content"] in ("-",content) and
         result["lease"] in ("-",packet["token"]) and result["stage"] in ("-",packet["token"]),
         "production-capsule-digests")
    return result

def prospective(lines,packet):
    if not lines:
        return [manifest_line(packet)]
    state = bound_history(lines,packet)
    snapshot,content = input_digests(packet)
    previous = lines[-1].split(b" ")[-1].decode() if len(lines)>1 else sha(lines[0])
    result = []
    for event in range(1,18):
        lease = packet["token"] if event in (2,15) else state["lease"]
        stage = packet["token"] if event == 6 else state["stage"]
        snap = snapshot if event == 4 else state["snapshot"]
        body = content if event == 5 else state["content"]
        prefix = f"EXRWH2 {len(lines)} {event} {lease} {stage} {snap} {body} {previous} {sha(lines[0])}".encode()
        candidate = prefix+b" "+sha(prefix).encode()
        try:
            bound_history([*lines,candidate],packet)
        except ValueError:
            continue
        result.append(candidate)
    need(result, "production-next-event")
    return result

def begin_record(lines,candidate,previous):
    row = bytearray(424)
    row[:8] = b"WH3INT01";row[8] = ord("B")
    struct.pack_into("<QQQ",row,16,len(lines)+1,len(lines),len(candidate))
    row[40:104] = sha(lines[0] if lines else candidate).encode()
    row[104:168] = sha(lines[-1]).encode() if lines else b"0"*64
    row[168:232] = sha(candidate).encode()
    row[296:360] = previous
    row[360:424] = sha(row[:360]).encode()
    return bytes(row)

def ack_record(begin):
    row = bytearray(begin)
    row[8] = ord("A")
    row[232:296] = row[296:360] = begin[360:424]
    row[360:424] = sha(row[:360]).encode()
    return bytes(row)

def acknowledged_prefix(journal,intents,packet):
    """Derive the last ACK; no complete ACK or contradictory suffix is ignored."""
    need(len(journal) <= 256*2051 and len(intents) <= 424*2*256+1, "repair-source-bound")
    original_intents = intents
    if intents.endswith(b"\xff"):
        intents = intents[:-1]
    lines = []
    jpos = ipos = keep_intent = 0
    previous = b"0"*64
    pending = None
    candidate = None
    while ipos+424 <= len(intents):
        row = intents[ipos:ipos+424]
        if pending is None:
            candidates = prospective(lines,packet)
            matched = [line for line in candidates if begin_record(lines,line,previous) == row]
            need(len(matched) == 1, "repair-complete-begin")
            candidate,pending = matched[0],row
        else:
            need(row == ack_record(pending), "repair-complete-ack")
            frame = struct.pack("<I",len(candidate))+candidate
            need(journal[jpos:jpos+len(frame)] == frame, "repair-acked-journal-bytes")
            jpos += len(frame);lines.append(candidate);keep_intent = ipos+424
            bound_history(lines,packet)
            candidate = pending = None
        previous = row[360:424]
        ipos += 424
    tail = intents[ipos:]
    if pending is not None:
        need(ack_record(pending).startswith(tail), "repair-partial-ack")
        frame = struct.pack("<I",len(candidate))+candidate
        need(len(journal)-jpos <= len(frame) and frame.startswith(journal[jpos:]), "repair-unacknowledged-frame-prefix")
    else:
        if tail:
            need(any(begin_record(lines,line,previous).startswith(tail) for line in prospective(lines,packet)),
                 "repair-partial-begin")
        need(len(journal) == jpos, "repair-journal-before-complete-begin")
    unack = len(original_intents) != keep_intent or len(journal) != jpos
    state = bound_history(lines,packet)
    need(native_pair(journal[:jpos],original_intents[:keep_intent],packet["binding"]["source"])["count"] == len(lines),
         "repair-independent-complete-prefix")
    return dict(state=state,lines=lines,journal_keep=jpos,intent_keep=keep_intent,unacknowledged=unack)

def gate_record(kind,sequence,generation,domain,manifest,count,tip,previous):
    row = bytearray(344)
    row[:8]=b"WH3GATE1";row[8]=ord(kind)
    struct.pack_into("<QQ",row,16,sequence,generation)
    row[32:80]=domain.encode();row[80:144]=manifest.encode()
    struct.pack_into("<Q",row,144,count)
    row[152:216]=tip.encode();row[216:280]=previous.encode()
    row[280:344]=sha(row[:280]).encode()
    return bytes(row)

def planned_gate(original,packet,ack):
    registry=packet["registry"];zero="0"*64
    initial=gate_record("I",1,0,registry["domain"],zero,0,zero,zero)
    need(initial[280:344].decode()==registry["seal"] and original[:344]==initial, "repair-independent-initial-gate")
    begin=gate_record("B",2,1,registry["domain"],sha(manifest_line(packet)),0,zero,registry["seal"])
    rest=original[344:]
    if not rest:
        need(not ack["lines"] and not ack["unacknowledged"], "repair-initial-no-effects")
        return initial
    if len(rest)<=344:
        need(begin.startswith(rest), "repair-interrupted-begin-prefix")
        if len(rest)<344:
            need(not ack["lines"] and not ack["unacknowledged"], "repair-no-cap-before-pending")
        return initial+begin
    need(rest[:344]==begin and not ack["unacknowledged"] and ack["state"]["event"]==12,
         "repair-clean-after-complete-terminal")
    state=ack["state"]
    clean=gate_record("C",3,1,registry["domain"],state["manifest_sha"],state["count"],
                      state["last_line_sha"],begin[280:344].decode())
    need(len(rest)-344<=344 and clean.startswith(rest[344:]), "repair-interrupted-clean-prefix")
    return initial+begin+(clean if len(rest)==688 else b"")

def repair_record(data,packet):
    need(len(data)==2939 and data[:8]==b"WH3RPR01", "repair-plan-schema")
    need(ztext(data[2874:2939]) == sha(data[:2874]), "repair-plan-seal")
    registry=registry_binding(data[8:1360])
    need(registry==packet["registry"] and ztext(data[1360:1425])==sha(packet["raw"]), "repair-input-authority")
    nonce=ztext(data[1425:1458]);predecessor=ztext(data[2809:2874])
    need(hexadecimal(nonce,32) and hexadecimal(predecessor,64), "repair-plan-identities")
    archives=[native_file(data[1458+n*97:1555+n*97]) for n in range(3)]
    keep=struct.unpack_from("<QQQ",data,1749)
    size=struct.unpack_from("<I",data,1773)[0]
    need(size in (344,688,1032) and keep[0]==size and not any(data[1777+size:2809]), "repair-plan-canonical-target")
    need(all(row["size"]<=64*1024*1024 for row in archives) and
         keep[1]<=archives[1]["size"] and keep[2]<=archives[2]["size"], "repair-plan-bounds")
    need(len({row["identity"] for row in archives})==3 and all(
        row["identity"] not in registry["identities"] for row in archives), "repair-fresh-archive-identities")
    return dict(nonce=nonce,predecessor=predecessor,seal=ztext(data[2874:2939]),
                archives=archives,keep=keep,target=data[1777:1777+size])

def audit_repairs(files,root,values,packet,detail):
    plans={}
    active=None
    for name,data in values.items():
        if not isinstance(data,bytes) or not data.startswith(b"WH3RPR01"):
            continue
        registry=registry_binding(data[8:1360])
        if registry["domain"]!=packet["registry"]["domain"]:
            continue
        plan=repair_record(data,packet)
        need(name=="Repair" or name=="Repair-"+plan["seal"], "repair-history-value-name")
        if plan["seal"] in plans:
            need(plans[plan["seal"]]==plan, "repair-identical-history")
        plans[plan["seal"]]=plan
        if name=="Repair":
            active=plan
    evidence=[]
    archive_tamper=detail.get("tamper","").startswith("archive-")
    ack_floor=detail.get("tamper")=="ack-floor"
    for plan in plans.values():
        if plan["predecessor"]!="0"*64:
            need(plan["predecessor"] in plans, "repair-predecessor-history")
        original=[]
        altered=[]
        for index,record in enumerate(plan["archives"]):
            name=root+f"/repair-{plan['nonce']}-{index}.raw"
            data=files[name]
            valid=len(data)==record["size"] and sha(data)==record["sha256"]
            if not valid:
                need(archive_tamper and index==1 and detail["tamper"]=="archive-bytes",
                     "repair-archive-bytes")
                need(len(data)>record["size"] and sha(data[:record["size"]])==record["sha256"],
                     "repair-planted-archive-tail")
                altered.append(name)
                data=data[:record["size"]]
            original.append(data)
        ack=acknowledged_prefix(original[1],original[2],packet)
        target=planned_gate(original[0],packet,ack)
        need(plan["keep"]==(len(target),ack["journal_keep"],ack["intent_keep"]) and
             plan["target"]==target, "repair-independent-plan-target")
        evidence.append(dict(seal=plan["seal"],original_sha=[sha(data) for data in original],
                             retained_count=len(ack["lines"]),altered_archives=altered))
    if archive_tamper:
        need(active is not None and plans and detail["remains_pending"] is True, "repair-negative-active-authority")
        need(values.get("RepairApplied") != active["seal"].encode()+b"\0", "repair-negative-never-applied")
        need(detail["raw_before"] == {name:sha(files[root+"/"+name])
              for name in ("admission.bin","journal.bin","intent.bin")}, "repair-negative-sources-unchanged")
    elif ack_floor:
        need(active is not None and detail["remains_pending"] is True and
             values.get("RepairApplied")==active["seal"].encode()+b"\0", "repair-rollback-active-ack-floor")
        current=acknowledged_prefix(files[root+"/journal.bin"],files[root+"/intent.bin"],packet)
        need(not current["unacknowledged"] and current["state"]["count"]==detail["kept_acks"] and
             active["keep"][2]//848==detail["protected_acks"] and detail["kept_acks"]<detail["protected_acks"],
             "repair-rejects-previous-complete-ack-prefix")
        need(files[root+"/admission.bin"]==active["target"], "repair-ack-floor-gate-preserved")
        need(detail["reverted"]=={name:sha(files[root+"/"+name])
             for name in ("admission.bin","journal.bin","intent.bin")}, "repair-refusal-no-further-source-write")
        need(detail["native_inodes"]==[int.from_bytes(packet["registry"]["identities"][n][8:],"little")
             for n in (2,3)], "repair-rollback-keeps-exact-native-objects")
    elif plans:
        need(active is None, "repair-retired-only-after-terminal-proof")
        need(all(digest in {digest for plan in evidence for digest in plan["original_sha"]}
                 for digest in detail.get("raw_before",{}).values()), "repair-originals-preserved")
    return evidence

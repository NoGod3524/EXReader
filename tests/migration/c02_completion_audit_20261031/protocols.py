# SPDX-License-Identifier: MIT
"""Independent, read-only decoders for the C02 evidence formats.
No production parser or verifier is imported.
"""
import hashlib
import json
import pathlib
import re
import sqlite3
import struct

SDK = "8357eafa28423a7ab93ba08b823af80f01ad1505"
C01 = "ccd7fec67eb8aa463b09533ce320820f2da472d9"
ABI2_FAILURES = [
    "FAIL recover-absent-prefix: status=completed detail=durable-commit-then-release",
    "FAIL recover-absent-prefix: appended to absent recovery prefix",
    "FAIL recover-absent-prefix: acted on an unbound journal",
    "FAIL recover-stale-prefix: status=rolled_back detail=durable-abort-then-release",
    "FAIL recover-stale-prefix: stale recovery mutated actual journal",
    "FAIL recover-stale-prefix: stale prefix allowed discard/release",
]

def need(value, label):
    if not value:
        raise ValueError(label)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def hexadecimal(value, size):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % size, value) is not None

def integer(value):
    return type(value) is int and value >= 0

def json_value(data):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "duplicate-json-key:" + key)
            result[key] = value
        return result
    def bad_constant(value):
        raise ValueError("nonfinite-json:" + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=bad_constant)

def summary(data):
    rows = [json_value(line) for line in data.decode("utf-8-sig").splitlines()
            if line.startswith('{"source":')]
    need(len(rows) == 1, "one-result-record")
    return rows[0]

def frames(data):
    result = []
    position = 0
    while position < len(data):
        need(position + 4 <= len(data), "torn-frame-header")
        size = struct.unpack_from("<I", data, position)[0]
        position += 4
        need(0 < size < 2048 and position + size <= len(data), "torn-frame-body")
        line = data[position:position + size]
        need(b"\0" not in line and len(result) < 256, "noncanonical-frame")
        result.append(line)
        position += size
    return result

MANIFEST_KEYS = ["source", "run", "attempt", "artifact", "platform", "sdk", "provider",
                 "admission", "publisher", "recovery", "observer", "fault"]

def manifest(line):
    fields = line.decode("ascii").split("|")
    need(len(fields) == 13 and fields[0] == "EXRWH2", "manifest-shape")
    result = {}
    for expected, field in zip(MANIFEST_KEYS, fields[1:]):
        key, sep, value = field.partition("=")
        need(sep and key == expected, "manifest-key-order")
        result[key] = value
    for key, size in [("source", 40), ("artifact", 64), ("provider", 64),
                      *[(key, 64) for key in MANIFEST_KEYS[7:]]]:
        need(hexadecimal(result[key], size), "manifest-hex:" + key)
    need(re.fullmatch(r"[0-9]{1,20}", result["run"]) is not None, "manifest-run")
    need(re.fullmatch(r"[0-9]{1,3}", result["attempt"]) is not None, "manifest-attempt")
    for key, maximum in [("platform", 31), ("sdk", 63)]:
        need(re.fullmatch(r"[A-Za-z0-9_.-]{1,%d}" % maximum, result[key]) is not None,
             "manifest-token:" + key)
    return result

def history(lines, source=None):
    if not lines:
        return dict(count=0, event=0, publish_intent=False, committed=False, aborted=False)
    need(len(lines) <= 256, "journal-line-bound")
    binding = manifest(lines[0])
    if source is not None:
        need(binding["source"] == source, "journal-source")
    bind = previous = sha(lines[0])
    old = 0
    lease = stage = snapshot = content = "-"
    published = committed = aborted = publish_intent = False
    for seq, line in enumerate(lines[1:], 1):
        text = line.decode("ascii")
        parts = text.split(" ")
        need(len(parts) == 10 and parts[0] == "EXRWH2", "event-shape")
        need(parts[1] == str(seq), "event-sequence")
        event = int(parts[2])
        need(parts[2] == str(event) and 1 <= event <= 17, "event-canonical-number")
        new_lease, new_stage, new_snapshot, new_content, prev, bound, seal = parts[3:]
        need(prev == previous and bound == bind and hexadecimal(seal, 64), "event-chain")
        need(sha(line.rsplit(b" ", 1)[0]) == seal, "event-seal")
        allowed = (
            event == 15 or
            event == 16 and old == 15 and publish_intent and not aborted or
            event == 17 and old == 15 and not published and not committed or
            event == 11 and old in (10, 16) or
            event == 12 and old in (11, 14) or
            event == 13 and old in (2, 3, 4, 5, 6, 7, 8, 9, 17) or
            event == 14 and old == 13 or
            event <= 10 and event == old + 1)
        need(allowed, "event-transition")
        if event in (2, 15):
            need(hexadecimal(new_lease, 48) and (lease == "-" or new_lease == lease), "lease-binding")
        else:
            need(new_lease == lease, "lease-preserved")
        if event == 6:
            need(stage == "-" and hexadecimal(new_stage, 48), "stage-binding")
        else:
            need(new_stage == stage, "stage-preserved")
        if event == 4:
            need(snapshot == "-" and hexadecimal(new_snapshot, 64), "snapshot-binding")
        else:
            need(new_snapshot == snapshot, "snapshot-preserved")
        if event == 5:
            need(content == "-" and hexadecimal(new_content, 64), "content-binding")
        else:
            need(new_content == content, "content-preserved")
        if event == 16:
            need(hexadecimal(new_stage, 48) and hexadecimal(new_content, 64), "recovery-content")
        lease, stage, snapshot, content = new_lease, new_stage, new_snapshot, new_content
        previous, old = seal, event
        publish_intent |= event == 9
        published |= event in (10, 16)
        committed |= event == 11
        aborted |= event == 14
    return dict(count=len(lines), event=old, binding=binding, manifest_sha=bind,
                last_line_sha=sha(lines[-1]), lease=lease, stage=stage,
                snapshot=snapshot, content=content, publish_intent=publish_intent,
                published=published, committed=committed, aborted=aborted)

def native_pair(journal, intents, source=None):
    lines = frames(journal)
    state = history(lines, source)
    need(len(intents) % 424 == 0 and len(intents) <= 424 * 2 * 256, "torn-intent")
    previous = b"0" * 64
    sequence = count = 0
    pending = begin_hash = None
    for offset in range(0, len(intents), 424):
        record = intents[offset:offset + 424]
        need(record[:8] == b"WH3INT01" and record[9:16] == b"\0" * 7, "intent-header")
        need(record[296:360] == previous, "intent-previous")
        digest = sha(record[:360]).encode()
        need(record[360:424] == digest, "intent-seal")
        number, old, size = struct.unpack_from("<QQQ", record, 16)
        if record[8:9] == b"B":
            need(pending is None and number == sequence + 1 and old == count and old < len(lines),
                 "intent-contiguous-begin")
            need(size == len(lines[old]) and record[232:296] == b"\0" * 64, "intent-begin-canonical")
            need(record[40:104] == sha(lines[0]).encode(), "intent-manifest")
            need(record[104:168] == (sha(lines[old - 1]).encode() if old else b"0" * 64), "intent-old-tip")
            need(record[168:232] == sha(lines[old]).encode(), "intent-new-tip")
            pending, begin_hash = record, digest
        elif record[8:9] == b"A":
            need(pending is not None and number == struct.unpack_from("<Q", pending, 16)[0],
                 "intent-ack-sequence")
            need(record[24:232] == pending[24:232] and record[232:296] == begin_hash, "intent-ack-binding")
            count, sequence, pending = old + 1, number, None
        else:
            raise ValueError("intent-kind")
        previous = digest
    need(pending is None and count == len(lines), "unacknowledged-journal")
    return state

def gate_records(data, expected_domain=None):
    need(0 < len(data) <= 344 * 256 and len(data) % 344 == 0, "gate-size")
    previous = b"0" * 64
    state = None
    generation = count = 0
    result = []
    for index, offset in enumerate(range(0, len(data), 344), 1):
        row = data[offset:offset + 344]
        need(row[:8] == b"WH3GATE1" and row[9:16] == b"\0" * 7, "gate-header")
        sequence, number = struct.unpack_from("<QQ", row, 16)
        domain = row[32:80].decode("ascii")
        bound = row[80:144].decode("ascii")
        size = struct.unpack_from("<Q", row, 144)[0]
        tip = row[152:216].decode("ascii")
        need(sequence == index and row[216:280] == previous, "gate-chain")
        need(hexadecimal(domain, 48) and hexadecimal(bound, 64) and hexadecimal(tip, 64), "gate-hex")
        if expected_domain is None:
            expected_domain = domain
        need(domain == expected_domain, "gate-domain")
        need(row[280:344] == sha(row[:280]).encode(), "gate-seal")
        kind = row[8:9]
        if index == 1:
            need(kind == b"I" and number == 0 and size == 0 and bound == "0" * 64 and tip == "0" * 64,
                 "gate-initial")
        elif kind == b"B":
            need(state != b"B" and number == generation + 1 and size <= 256, "gate-begin")
            count = size
        elif kind == b"C":
            need(state == b"B" and number == generation and count <= size <= 256 and bound == result[-1]["manifest"],
                 "gate-clean")
        else:
            raise ValueError("gate-transition")
        result.append(dict(kind=kind.decode(), generation=number, count=size, manifest=bound, tip=tip,
                           seal=row[280:344].decode(), domain=domain))
        previous, state, generation = row[280:344], kind, number
    return result

def ztext(data):
    value, sep, tail = data.partition(b"\0")
    need(sep and not any(tail), "padded-text")
    return value.decode("ascii")

def wtext(data):
    need(len(data) % 2 == 0, "wide-size")
    units = [data[n:n + 2] for n in range(0, len(data), 2)]
    need(b"\0\0" in units, "wide-termination")
    index = units.index(b"\0\0")
    need(all(unit == b"\0\0" for unit in units[index:]), "wide-padding")
    value = b"".join(units[:index]).decode("utf-16le")
    need(value and "\0" not in value, "wide-text")
    return value

def registry_binding(data):
    need(len(data) == 1352 and data[:8] == b"WH3REG01" and data[-64:] == sha(data[:-64]).encode(),
         "registry-binding-seal")
    domain = data[8:56].decode("ascii")
    need(hexadecimal(domain, 48), "registry-domain")
    identities = [data[128 + n * 24:152 + n * 24] for n in range(5)]
    need(domain == identities[0].hex(), "registry-native-domain")
    library, root = wtext(data[248:768]), wtext(data[768:1288])
    for path in (library, root):
        need(re.fullmatch(r"[A-Za-z]:\\[^\r\n]+", path) is not None, "registry-absolute-path")
        need(all(part not in (".", "..") for part in pathlib.PureWindowsPath(path).parts), "registry-path-components")
    seal = data[64:128].decode("ascii")
    need(hexadecimal(seal, 64), "registry-grant")
    return dict(domain=domain, identities=identities, library=library, root=root,
                generation=struct.unpack_from("<Q", data, 56)[0], seal=seal)

def transaction(data, phase):
    need(len(data) >= 1440 and data[:8] == b"WH3TXN01" and data[-64:] == sha(data[:-64]).encode(),
         "transaction-envelope")
    kind, size = struct.unpack_from("<QQ", data, 8)
    need(kind == phase and 0 < size <= 65536 and size == len(data) - 1440, "transaction-size")
    return registry_binding(data[24:1376]), data[1376:-64]

def native_file(data, absent=False):
    if absent:
        need(data == b"\0" * 97, "absent-file-canonical")
        return None
    need(len(data) == 97, "native-file-size")
    digest = ztext(data[32:97])
    need(hexadecimal(digest, 64), "native-file-sha")
    return dict(identity=data[:24], size=struct.unpack_from("<Q", data, 24)[0], sha256=digest)

def input_record(data, source, run, attempt):
    registry, raw = transaction(data, 1)
    need(len(raw) == 2577 and raw[:8] == b"C02IN001", "input-schema")
    ranges = [(8,49),(49,70),(70,78),(78,143),(143,175),(175,239),(239,304)]
    names = ["source","run","attempt","artifact","platform","sdk","provider"]
    binding = dict(zip(names, [ztext(raw[a:b]) for a,b in ranges]))
    need(binding["source"] == source and binding["run"] == str(run) and binding["attempt"] == str(attempt),
         "input-producer")
    need(binding["platform"] == "windows-ntfs" and binding["sdk"] == "3.42.0-8357eafa",
         "input-platform-sdk")
    need(hexadecimal(binding["artifact"],64) and hexadecimal(binding["provider"],64), "input-hashes")
    gates = [ztext(raw[304+n*65:369+n*65]) for n in range(5)]
    need(all(hexadecimal(item,64) for item in gates), "input-gates")
    pack, library = wtext(raw[629:1149]), wtext(raw[1149:1669])
    stages = [wtext(raw[1669+n*128:1797+n*128]) for n in range(2)]
    retained = [wtext(raw[1925+n*128:2053+n*128]) for n in range(2)]
    token = ztext(raw[2181:2230])
    mirror_present, partial = struct.unpack_from("<II",raw,2569)
    need(hexadecimal(token,48) and mirror_present in (0,1) and partial in (0,1), "input-flags")
    need(stages == [f"c02-{token}-{n}.stage" for n in range(2)] and
         retained == [f"c02-{token}-{n}.retained" for n in range(2)], "input-private-leaves")
    original = native_file(raw[2230:2327])
    mirror = native_file(raw[2327:2424],not mirror_present)
    pack_file = native_file(raw[2424:2521])
    staged = [raw[2521+n*24:2545+n*24] for n in range(2)]
    need(registry["library"] == library and registry["identities"][4] == original["identity"],
         "input-registered-target")
    need(registry["generation"] == 0, "input-fresh-epoch")
    need(len(set([original["identity"],*staged])) == 3, "input-distinct-targets")
    return dict(registry=registry, raw=raw, binding=binding, gates=gates, pack=pack, library=library,
                stages=stages, retained=retained, token=token, original=original, mirror=mirror,
                pack_file=pack_file, staged=staged, allow_partial=bool(partial))

def prepared_record(data, original):
    registry, raw = transaction(data,2)
    need(len(raw) == 267 and raw[:8] == b"C02OUT01", "prepared-schema")
    need(ztext(raw[8:73]) == sha(original["raw"]) and registry == original["registry"], "prepared-input-binding")
    files = [native_file(raw[73+n*97:170+n*97]) for n in range(2)]
    need(all(row["identity"] == expected and row["size"] > 0
             for row,expected in zip(files,original["staged"])), "prepared-identities")
    return files

def legacy_pack(data):
    need(len(data) >= 64 and data[:8] == b"EXRLGP1\n" and data[-56:-48] == b"EXRLGPT1", "pack-header")
    offset,size = struct.unpack_from("<QQ",data,len(data)-48)
    need(8 <= offset and size <= 64*1024*1024 and offset+size+56 == len(data), "pack-bound")
    raw = data[offset:offset+size]
    need(hashlib.sha256(raw).digest() == data[-32:], "pack-manifest-sha")
    result = json_value(raw)
    need(result["format"] == "exreader-legacy-pack" and result["version"] == 1, "pack-version")
    need(result["counts"] == dict(books=len(result["books"]),notes=len(result["notes"])), "pack-counts")
    for row in result["books"]:
        file = row["file"]
        if file["present"]:
            start,length = file["offset"],file["size"]
            need(integer(start) and integer(length) and 8 <= start <= offset and length <= offset-start,
                 "pack-original-bound")
            need(file["sha256"] == sha(data[start:start+length]), "pack-original-sha")
    return result

def sqlite_content(database, mirror, pack, expected_txt=None):
    ledger = json_value(mirror)
    need(ledger["format"] == "exreader-legacy-map" and ledger["version"] == 1, "ledger-format")
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(database)
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA query_only=ON")
        need(connection.execute("PRAGMA application_id").fetchone() == (1163416131,), "sqlite-application")
        need(connection.execute("PRAGMA user_version").fetchone() == (7,), "sqlite-version")
        need(connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)], "sqlite-integrity")
        rows = connection.execute("SELECT data FROM exr_migration_ledger WHERE id=1").fetchall()
        need(len(rows) == 1 and bytes(rows[0][0]) == mirror, "sqlite-native-ledger-equals-mirror")
        books = {row["legacy_id"]:row for row in ledger["books"]}
        notes = {row["legacy_id"]:row for row in ledger["notes"]}
        need(len(books)==len(ledger["books"]) and len(notes)==len(ledger["notes"]), "ledger-unique-legacy-identities")
        if expected_txt is not None and "b-txt" in books:
            actual=connection.execute("SELECT source FROM books WHERE id=?",(books["b-txt"]["book_id"],)).fetchone()
            need(actual is not None and bytes(actual[0])==expected_txt, "sqlite-qualified-txt-fixture")
        for item in pack["books"]:
            mapped = books.get(item["legacy_id"])
            if not item["file"]["present"]:
                continue
            need(mapped is not None and mapped["sha256"] == item["file"]["sha256"], "sqlite-book-mapping")
            if mapped["kind"] == "audio":
                continue
            actual = connection.execute("SELECT source FROM books WHERE id=?",(mapped["book_id"],)).fetchall()
            need(len(actual) == 1 and sha(bytes(actual[0][0])) == item["file"]["sha256"], "sqlite-actual-original")
        for item in pack["notes"]:
            mapped = notes.get(item["legacy_id"])
            need(mapped is not None and mapped["retained"]==item["record"], "sqlite-note-mapping")
            if not mapped["located"]:
                need(mapped["new_id"] is None, "sqlite-unlocated-no-identity")
                continue
            owner = books[mapped["book_legacy_id"]]
            record = item["record"]
            comment = record.get("note","")
            if mapped["kind"] == "reflow":
                if record.get("bookmark") and not comment:
                    comment = record["quote"]
                actual = connection.execute("SELECT book_id,start,end,text FROM notes WHERE id=?",
                                            (mapped["new_id"],)).fetchall()
                need(actual == [(owner["book_id"],mapped["start"],mapped["end"],comment)], "sqlite-actual-reflow-note")
            elif mapped["kind"] == "fixed":
                actual = connection.execute("SELECT book_id,page,start,end,text FROM fixed_notes WHERE id=?",
                                            (mapped["new_id"],)).fetchall()
                need(actual == [(owner["book_id"],mapped["page"],mapped["start"],mapped["end"],comment)],
                     "sqlite-actual-fixed-note")
            elif mapped["kind"] == "audio":
                actual = connection.execute("SELECT audio_id,track_id,offset,label FROM audio_marks WHERE id=?",
                                            (mapped["new_id"],)).fetchall()
                need(len(actual) == 1 and actual[0][0] == owner["audio_id"] and
                     actual[0][1] == mapped["book_legacy_id"] and
                     int.from_bytes(actual[0][2],"little") == mapped["start"] and
                     actual[0][3] == (comment or record["quote"]), "sqlite-actual-audio-note")
        if "n-txt-unique" in notes:
            one = notes["n-txt-unique"]
            actual = connection.execute("SELECT anchor_exact,text FROM notes WHERE id=?",(one["new_id"],)).fetchone()
            need(actual == ("unique sentence about silver tides","keep this"), "sqlite-independent-unique-note")
        if "n-txt-ambiguous" in notes:
            missing = notes["n-txt-ambiguous"]
            owner = books[missing["book_legacy_id"]]
            need(not missing["located"] and missing["reason"] == "quote-ambiguous" and
                 connection.execute("SELECT count(*) FROM notes WHERE book_id=? AND text=?",
                                    (owner["book_id"],"appears twice")).fetchone() == (0,),
                 "sqlite-independent-ambiguous-note")
        return dict(ledger_sha256=sha(mirror),books=len(books),notes=len(notes))
    finally:
        connection.close()

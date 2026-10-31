# SPDX-License-Identifier: MIT
"""Independently reconstruct the read-only scanner's retained input observations."""
import struct

from protocols import need, sha, summary, frames, native_pair, gate_records, json_value, hexadecimal, integer

def audit_scanner(files,spec,source,missing):
    result=summary(files["repair-scan.log"])
    expected=spec.get("expected_scanner")
    if expected is None:
        missing.add("scanner-current-exact-count-adapter")
        expected=dict(cases=29,checks=91794,observations=6603)
    need(expected["cases"]>=29 and expected["checks"]>=91794 and expected["observations"]>=6603,
         "scanner-preserved-observation-floor")
    need(result["source"]==source and result["failed"]==0 and result["passed"] is True and
         all(result[key]==expected[key] for key in ("cases","checks","observations")), "scanner-current-counts")
    need(result["native_io"] is True and result["read_only_scanner"] is True and
         result["process_kill"] is False and result["production_repair"] is False, "scanner-evidence-scope")
    journal=files["repair-scan/native/journal.bin"]
    intents=files["repair-scan/native/intent.bin"]
    state=native_pair(journal,intents,source)
    lines=frames(journal)
    need(state["count"]==13 and state["event"]==12 and state["committed"], "scanner-reference-real-native-history")
    gate=gate_records(files["repair-scan/native/admission.bin"],"2"*48)
    need(len(gate)==3 and gate[-1]["kind"]=="C" and gate[-1]["count"]==13 and
         gate[-1]["tip"]==state["last_line_sha"] and gate[-1]["manifest"]==state["manifest_sha"],
         "scanner-reference-native-gate")
    ends=[0]
    for line in lines:
        ends.append(ends[-1]+4+len(line))
    negative={}
    for index in range(1,20):
        j=files[f"repair-scan/negative-{index:02}-journal.bin"]
        i=files[f"repair-scan/negative-{index:02}-intent.bin"]
        try:
            native_pair(j,i,source)
        except ValueError:
            pass
        else:
            raise ValueError("scanner-preserved-negative-accepted")
        negative[(len(j),len(i),sha(j),sha(i))]=(j,i)
    observations=[json_value(line) for line in files["repair-scan/observations.jsonl"].splitlines() if line]
    need(len(observations)==result["observations"] and
         [row["observation"] for row in observations]==list(range(1,len(observations)+1)),
         "scanner-every-observation")
    accepted=rejected=0
    observed_cases=set()
    def legal_prefix(j,i):
        if i.endswith(b"\xff"):
            i=i[:-1]
        count,remainder=divmod(len(i),848)
        if count>13 or not intents.startswith(i) or not journal.startswith(j):
            return False,0
        if remainder==0:
            return len(j)==ends[count],count
        if count==13:
            return False,0
        if remainder<424:
            return len(j)==ends[count],count
        if remainder==424:
            return ends[count]<=len(j)<=ends[count+1],count
        return len(j)==ends[count+1],count
    for row in observations:
        observed_cases.add(row["case"])
        jsize,isize=row["journal_bytes"],row["intent_bytes"]
        need(integer(jsize) and integer(isize) and hexadecimal(row["journal_sha256"],64) and
             hexadecimal(row["intent_sha256"],64) and type(row["accepted"]) is bool, "scanner-observation-schema")
        key=(jsize,isize,row["journal_sha256"],row["intent_sha256"])
        candidates=[]
        # The source fixture bytes are retained once; each cut is reconstructed
        # from its recorded lengths, then independently checked against both hashes.
        if jsize<=len(journal) and isize<=len(intents):
            candidates.append((journal[:jsize],intents[:isize]))
        if jsize<=len(journal) and 1<=isize<=len(intents)+1:
            candidates.append((journal[:jsize],intents[:isize-1]+b"\xff"))
        if key in negative:
            candidates.append(negative[key])
        name=row["case"]
        if name=="partial-ACK-needs-complete-journal-and-exact-canonical-prefix":
            i=bytearray(intents[:isize])
            if len(i)>5*848+424+16:
                i[5*848+424+16]^=1
                candidates.append((journal[:jsize],bytes(i)))
        if name=="partial-BEGIN-rejects-complete-known-field-conflict":
            i=bytearray(intents[:isize]);i[5*848+9]=1
            candidates.append((journal[:jsize],bytes(i)))
        if name=="partial-body-must-prefix-a-legal-canonical-next-line":
            j=bytearray(journal[:jsize]);j[ends[5]+4]=ord("X")
            candidates.append((bytes(j),intents[:isize]))
        if name=="two-append-tails-and-extra-poison-are-not-one-interruption":
            candidates.append((b"",b"\xff\xff"))
        matched=[pair for pair in candidates if (len(pair[0]),len(pair[1]),sha(pair[0]),sha(pair[1]))==key]
        need(matched, "scanner-raw-observation-reconstructable")
        pair=matched[0]
        legal,count=legal_prefix(*pair)
        need(legal is row["accepted"], "scanner-independent-prefix-verdict")
        if legal:
            need(row["count"]==count and row["expected_count"]==count, "scanner-last-complete-ack-count")
            native_pair(pair[0][:ends[count]],pair[1][:count*848],source)
            accepted+=1
        else:
            need(row["count"]==0 and row["expected_count"]==0, "scanner-rejected-output-cleared")
            rejected+=1
    need(accepted>0 and rejected>0 and len(negative)==19, "scanner-positive-and-negative-coverage")
    return dict(cases=result["cases"],checks=result["checks"],observations=len(observations),
                independently_reconstructed_accepted=accepted,independently_reconstructed_rejected=rejected,
                retained_semantic_negative_pairs=19,observation_case_names=sorted(observed_cases))

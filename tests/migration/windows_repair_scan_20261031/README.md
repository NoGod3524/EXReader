# C02 last-ACK observational scanner fixtures

This separate Windows consumer reads actual native journal, intent and admission bytes.
It generates the canonical 13-line fixture through the unchanged coordinator and
writes its baseline using the actual wh3wg/wh3w native APIs. The baseline native
three-file set is retained under the requested evidence directory.

The 29 named scenarios cover every complete ACK prefix; every byte boundary of
partial BEGIN and ACK records at three history positions; every partial journal
frame/body boundary there; the native poison byte; exact canonical pending/clean
admission prefixes; and resealed semantic contradictions. Successful observations
check exact native identities, original sizes and SHA256, acknowledged boundaries,
canonical lines and byte-for-byte absence of source mutation. The observation
matrix is preserved in observations.jsonl. Nineteen resealed negative raw pairs
are retained as separate files.

These are deterministic byte-prefix fixtures. The summary explicitly records
process_kill=false and production_repair=false. Root's actual owner process-kill
and protected registry Repair-plan tests supply those integration proofs.

## Root integration

Add src/wh3_repair_scan.c to the installed native library and install
include/exr_wh3_repair.h alongside exr_wh3_win.h. The new consumer needs no SDK:
compile repair_scan_test.c as C11 with the same MT runtime, _WIN32_WINNT=0x0602,
_CRT_SECURE_NO_WARNINGS and CANDIDATE_SOURCE_SHA set to the exact Actions source.
Use /utf-8 /W4 /WX and link the installed native, CAS and hardening libraries
plus advapi32, using their three installed include directories.

Invoke coordinator-repair-scan-check NEW_EVIDENCE_DIRECTORY from Actions.
The parent directory must exist; the leaf must not exist. Keep its stdout and
the entire evidence directory, including native/, observations.jsonl and all
negative raw pairs. A successful summary reports cases=29, failed=0 and
passed=true. Do not infer success from these expected values before executing.

The optional observation entry point is:
coordinator-repair-scan-check --observe JOURNAL INTENT ORIGINAL_SOURCE_SHA
It opens existing raw files read-only, uses the fixture's original canonical
binding/gates with the explicitly supplied 40-byte source SHA, and emits
acceptance, count, keep boundaries and unack_tail. It creates no fixture or
repair object and returns 0 for accepted evidence, 2 for refusal.

## API boundary

wh3r_scan_ack consumes two already identified, exclusively held handles and
the original binding/gates. The large wh3r_scan output must live on the heap.
It makes two independent complete byte reads, checking native identities and
sizes again. Every complete ACK is included; a complete contradictory record
is refused. A single legal interrupted append and optional native poison byte
may follow the acknowledged prefix. It never writes or grants a capability.

wh3r_scan_gate consumes the independently trusted initial I0 grant and a fresh
successful ACK observation made under the same custody. It accepts one I/B/C
epoch only. A partial B with an entirely empty raw pair plans a full canonical
PENDING B. A partial C requires an exact terminal ACK and plans I+B; a complete
C is preserved. C plus an unacknowledged journal/intent tail is contradictory.
The result includes original identity/size/SHA and the exact planned target;
the caller still needs the protected Repair plan, durable full raw archives,
identity checks and later actual publication/abort proof. This component does
not perform truncation, gate writes, registry updates or a CLEAN transition.

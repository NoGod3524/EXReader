# Restart acquired-window failure candidate

Base: 638976413692412fd7cc15d7e508d0382d1faffd (documentation child of tested
6db7c3dc1005c7fd22f91b02a150bfdd671f723c).
Branch: codex/p0-win-restart-window-lock-20261030.

The only production control-flow change routes a failed first lease_window to
done rather than fail after lm_wl_acquire has succeeded. It returns a retained
REFUSED object, preserving EXCLUSIVE until explicit lm_rr_close. No admission,
COMMIT, pending clear, automatic retry, or permanent lock is introduced.
Before-acquire failures still return zero and NULL and release their pins.
The result generation/pending fields have not been populated at this point;
their zero values do not describe the disk. Evidence snapshots the open-time
reason/native code before lm_rr_check can report restart-not-qualified.

The public header, production CMake, original workflow, original probe and
original 26-case runner are unchanged. The new after-acquire hook is compiled
only under LM_RR_TEST_AFTER_ACQUIRE, a PRIVATE definition of the independent
window_lock executable. That target directly compiles the same restart source,
does not link the installed restart archive, and is not installed. The normal
installed production library contains no new hook reference or definition.
The existing public pre-acquire lm_rr_set_window_probe API is not changed.

The new workflow retains the original installed 26 cases and older regressions,
then runs two independent real Windows range-lock cases:
- clean PENDING=1: after successful EXCLUSIVE acquisition a helper locks [0,80);
  the reader refuses with restart-lease-window and retains its object. After the
  helper unlocks, shared is still BUSY due to EXCLUSIVE. Explicit close leaves
  shared STALE, and a fresh reader succeeds, proving no permanent handle leak.
- drift: the helper writes generation=5/PENDING=0 after acquisition, then locks
  [0,80). Refusal retains EXCLUSIVE while alive without restoring bytes. After
  reader death the shared result is measured and a new reader refuses generation.
  No durable crash isolation is claimed; the missing persistent marker remains.

The fixture uses bounded pipe handshakes, not sleeps, to establish ordering.
Receipt separates unconfirmed result fields from actual lease-byte measurements.
Compile definitions, object/archive symbols and both link maps establish which
source variant ran. The two-case receipt remains separate from the unchanged
26-case receipt.

Status: single authorized Actions run passed; scope and residual limits below. Candidate only; 95/108 unchanged.

## Single authorized Actions result

Source: 43f2fd0f94cb820a4ed42ca99ab0906272ba8623.
Run: https://github.com/NoGod3524/EXReader/actions/runs/41146675121
Attempt 1; job 124373287391; windows-2022; completed success 2026-10-30T23:51:53Z.

The unchanged original 26-case runner completed successfully against the installed
production archive. The original record27, publication28+2cuts, bridge26+4cuts
and refusal8 steps also passed. Their existing assertions were not changed.
The original 26-case receipt is archived, not printed in the log; this review
used the unchanged assertions and successful step, and did not unpack the ZIP.

The independent two-case runner printed WINDOW-LOCK-SUMMARY cases=2 failed=0.
Both cases observed open_reason=restart-lease-window, open_native=33, a non-null
REFUSED object, checked=false, and exactly one after-acquire hook invocation.
The helper released its range lock and exited before shared exclusion was tested.
Both then measured shared status=2 (BUSY) while the refused reader object lived.

Clean case: disk remained generation=0/PENDING=1, SHA256
864005f505014779a5e860386025ad895486bc69beab14cf443d2cf261ddf040.
After explicit close, shared status=3 (STALE); a new installed reader succeeded
with class=3 and checked=true. No permanent handle exclusion remained.

Drift case: disk remained generation=5/PENDING=0 after the helper's deliberate
write, SHA256 7aeda2715f9b7eb449d3c93f6d1c7db440ea4c1066b429b34b908ad35d1d6a66.
After reader kill, shared status=0 (admitted), while a fresh installed reader
refused with restart-lease-generation. This is the measured remaining crash
isolation gap, NOT a durable-isolation pass or an SDK admission proof.
The returned result generation/pending zeroes were explicitly recorded as
unconfirmed fields, separate from actual disk observations.

Isolation verification passed in Actions:
- production compile definitions omit LM_RR_TEST_AFTER_ACQUIRE;
- production archive symbol dump contains no lm_rr_test_after_acquire;
- variant reader object has one UNDEF reference to that hook;
- variant probe object has one External definition;
- installed lm_rr_open map source:
  exreader-migration-windows-restart-reader:lm_win_restart_reader.obj;
- variant lm_rr_open map source: lm_win_restart_reader.obj (direct object);
- shared source file SHA256:
  92d7d41de4a53e312daff4e23de67fada168040b2847f3a0e3f901e70e82f2af.

Artifact: windows-restart-window-lock-43f2fd0f94cb820a4ed42ca99ab0906272ba8623,
ID 13021382398, 597584 bytes, GitHub ZIP digest SHA256
14feee6642fe5e4bcff17ccba738cd8d7ebedeb0872efb9904cf6d03a41343a8.
These are GitHub metadata and upload-log values; no local ZIP extraction or
re-hashing was performed. Receipts, symbol dumps, project definition evidence,
both consumer maps, installed archives and older evidence are archived together.

No rerun, second validation round, mainline push, PR, tag, release, C01 change,
SDK change, production-owner change, public-header change or old-test change.
Candidate classification evidence only; formal score remains 95/108.

# F05 paging raw evidence, 2026-10-30

Base cbe52cce90680cd043ca38ad0b1771ae6e66bd55.
Branch codex/dot-f05-paging-evidence-20261030.
Scope: paging.cpp, new dedicated workflow, this document only.
One authorized push/run; no diagnostic rerun without a bounded follow-on decision.

The unchanged 29 metadata, 8 GTK and 9 installed synthetic API checks remain.
No product, SDK, original workflow, old budgets or assertion has been removed.
The new workflow repeats the full original Linux pipeline, timeout 80 minutes.
calls.jsonl records the existing nine API invocations; setup.jsonl records
the existing 51 PUT/DELETE pairs. Wrappers invoke each original API once,
flush observations before the original assertion, and propagate original status.
File output errors fail the executable; stdout retains its original single JSON.
flush is not fsync and is not claimed as crash-persistence proof.

The Actions-only manifest records source/run/attempt and byte size/SHA256 for
calls.jsonl, setup.jsonl, catalog.sqlite and result.json, even on partial failure.
Always-upload preserves failure evidence. Raw pipeline failure remains failure.

This is producer evidence, not independent re-execution or independent audit.
The synthetic API is not GTK behavior, not SDK-original evidence, not full F05,
not six-platform acceptance. Formal acceptance remains 95/108.
The previous C07 audit of 73ac does not cover these new receipts.
No CI result is claimed until the dedicated run completes.

# Windows raw history capture: public boundary decision

The coordinator reported a private declaration in the Windows-owned bridge.
Core inspected Git object `e8ee47a2` without editing another team's worktree.
`apps/reader/desktop/windows_wave3.inc:900` calls `w3_encode_retained` for a
reflow/EPUB version-2 capture, then commits only the wire into jump history at
line 903. `windows_wave3_bridge.cpp:7` declares the non-public C++ symbol
`reader_rs_encode_retained_raw_v3`, marked internal command-only in
`apps/reader/reading-state/src/reading_state.cpp:245`.

## Existing public APIs

`reader_rc_apply_raw_v3` is public in
`apps/reader/reading-commands/include/reader_reading_commands.h:86`. It can
preserve actual anchor versions 1/2 and handles NOTE_TEXT by reading the source
version and checking the same location. It also commits a local reading revision
and outbox (`reading_commands.cpp:259`). It therefore covers intentional
persistent reading commands, but is not an equivalent replacement for this
encode-only history capture. Calling it solely to obtain a wire would change
business behavior.

`reader_rs_encode` and `reader_rs_encode_v2` retain their legacy-store contract.
The existing public raw codec `reader_rs_encode_fixed_v3` accepts fixed_page
only. Neither relabelling a reflow/EPUB v1/v2 wire as v3 nor mixing legacy/raw
stores is an acceptable repair.

## Minimal separate app-module candidate

Proposed raw reading-state package version: **0.3.0**. Preserve the existing
legacy 0.1.0 and raw 0.2.0 trees and their results. Add a public C-linkage function
under the existing raw capability macro:

```c
reader_rs_status reader_rs_encode_raw_v3(
  reader_revisions *, const reader_rs_envelope *, const reader_rs_capture *,
  unsigned anchor_version, size_t part,
  char **wire, size_t *bytes, reader_rs_error *);
```

Its contract is encode/validate only, with no revision, history or outbox write.
Require explicit version 1/2/3, with 3 restricted to fixed_page, and retain every
existing selector representability and byte-bound refusal. Reuse the existing
internal `encode(..., raw_api=true)` implementation; do not duplicate a JSON
serializer in the host. Output is released with `reader_rs_free`.

This is an **app reading-state API proposal**, not a frozen SDK change or an
implemented/accepted candidate. Current core guards bind reading-state and the
other protected modules exactly to `d263ce52`. Implementing and adopting it
requires an independent pinned candidate, explicit compatibility treatment of
dependent raw package EXACT-version/provenance guards, and same-source Actions
evidence for reflow/EPUB version preservation, fixed raw selectors, no writes,
and refusal of legacy/raw mixing. Do not silently relax those guards.

Windows owns removal of its private bridge declaration and the eventual public
call-site change after that independent candidate is approved and accepted.
Core has changed neither the Windows-owned source nor the seven protected
modules in this round.

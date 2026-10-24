# GTK library collections

The bookshelf's **More → Collections…** action opens a native GTK organizer.
`Ctrl+Shift+C` opens the same dialog. Shelves support children and explicit
positions; tags and series share the same typed metadata owner. Series and
shelf memberships have editable positions. The main bookshelf keeps its
existing layout, stable viewport anchor and 150-row cache.

## Controls and storage

Choose Shelves, Tags or Series, then create, rename, remove or restore a
collection. Enter a shelf to view its children; Up and Root navigate its
hierarchy. **Removed** lists retained deleted groups across every hierarchy
level, including historical records produced by another device or writer.
Group and member pages each contain at most 50 copied rows. Previous/Next
groups (`Ctrl+PageUp` / `Ctrl+PageDown`) and Earlier/Later books (`Alt+Left` /
`Alt+Right`) use exclusive native keyset cursors in both directions.

The book selected on the main bookshelf when the organizer opens is shown
above **Add selected book**. To classify another downloaded book, close the
organizer, select that book and reopen it. Any displayed member can be
removed or repositioned. Adding an existing removed membership explicitly
restores its retained history; its position is editable in the restore dialog.
Activating a downloaded member opens its
original through the normal public SDK path; a cloud-only member asks for
its original to be downloaded.

The existing worker owns all catalog and metadata handles, prepared
snapshots and commands. GTK receives copied text, IDs, row fields and a
single-use token. It writes no SQL, revision wire or network data. Before a
legacy book's first classification, the worker proves the retained SDK
original's format, SHA-256 and length. A separate bootstrap preserves the
current product title, author, favorite and sort title before preparing the
membership edit again.
The editor states that verification has retained the book details; Cancel
makes no membership change. A subsequent Save is one membership transaction.

Each mutation durably stages one complete typed intent with its original
heads before submitting it. A refused or interrupted transaction retains
those same bytes. The native recovery dialog requires explicit Retry or
Discard; it never binds the edit to newer heads. Discard cannot remove an
already committed intent. Window-manager close requests wait for the active
owner job; a committed result remains committed even if cleanup needs retry.
Native control focus is retained across worker jobs and moved to the copied
selected row after a list rebuild.

Restoring a child under a removed parent disables Save and offers **View
parent** (`Alt+V`). Restore the parent explicitly, then prepare the child again. The
organizer neither restores dependencies automatically nor chooses a conflict
head. Existing memberships survive group deletion and become visible again
after the group is restored.

## Cloud acceptance

Accepted feature source:
`b9124fbd49c5207eeba204414578dda2f0075e81` in
[40057786209](https://github.com/NoGod3524/EXReader/actions/runs/40057786209),
attempt 1, job `120764494096`, completed successfully.
The feature branch runs the Linux desktop workflow; the integrated workflow
retains its Linux and Windows matrix. Local operations are source/document
and Git work only.

| Same-source actual GTK suite | Passed |
| --- | ---: |
| Original operations | 20/20 |
| Product startup/ownership | 5/5 |
| Fixed PDF/CBZ | 24/24 |
| Bounded bookshelf | 14/14 |
| Book metadata and recovery | 15/15 |
| Collections and recovery | 27/27 |

The same job also passed 9/9 installed SDK and 12/12 native catalog checks,
two actual killed-process recovery stages, Linux backend 82 checks in 11
groups, private fixed snapshot 53 checks and bounded backend 82 checks. The
original four GTK refusal/regression groups remain successful. The frozen
SDK trees and product schema check passed before building.

Artifact `12545949051` is nonempty (39,285,410 bytes), unexpired and bound to
this same run and source. The completed upload digest equals the API digest:
`sha256:242152b70c7364a5dbf01fa4a14380702069844c9c047aae0bb42592a13ea59e`.
The collection report's SHA-256 is
`90703ddf22074a847d028cf7ffb8a537dc7560bcbd83f185bc27528e9a3f64d9`.
Seven named screenshots, the retained refused intent and three recovery
observations are included in its file manifest. The executable SHA-256,
seven screenshot hashes and all retained failed artifact identities are in
[reader-gtk-collections.json](validation/reader-gtk-collections.json).

`tests/linux_host/check_collections_ui.py` adds 27 actual GTK/X11 checks. They
cover group creation/rename/position/cancel, children, three membership
kinds, legacy original proof, membership removal/restoration, parent restore
dependencies, a real writer lock and native close request, actual transaction
refusal, host process death, unchanged pending bytes on restart, explicit
retry/discard, a concurrent native producer, 56 active tags, 55 historical
removed tags, 56 ordered series members, and opening the original from a
member row. Independent native typed producers create the paging fixtures;
test-only SQL observes effects and injects legacy state/refusal.

The original GTK 20 operations, product 5, fixed-page 24, shelf 14 and book
metadata 15 checks remain in the same workflow before these new checks.
Screenshots, application log, copied-row observation, SQLite test snapshot,
pending recovery evidence and native writer results belong to the same
source/run/attempt artifact. Results grant only the stated GTK collection
scope; sync settings, other platform UIs and performance budgets remain
separate acceptance work.

## Retained failed candidates

| Source | Run | Refusal and correction |
| --- | --- | --- |
| `50d47a42` | [40054652102](https://github.com/NoGod3524/EXReader/actions/runs/40054652102) | Strict compile rejected misleading indentation; split the independent state update onto its own line. |
| `78f89fd8` | [40054970154](https://github.com/NoGod3524/EXReader/actions/runs/40054970154) | Cancelling New lost the current group selection; only the prepared new command now receives an empty ID. |
| `0937b28d` | [40055547372](https://github.com/NoGod3524/EXReader/actions/runs/40055547372) | The Books mnemonic focused the list container without selecting a member; native mnemonics now focus/select an actual row. |
| `109c9f75` | [40056340641](https://github.com/NoGod3524/EXReader/actions/runs/40056340641) | View parent shared Alt+P with Position; its native mnemonic is now Alt+V. |
| `983c67d7` | [40057064804](https://github.com/NoGod3524/EXReader/actions/runs/40057064804) | Disabling the organizer during an asynchronous read lost the type selector focus; queue/result now retain and restore the native focused control. |

Every failed run and its original artifact remain retained. Earlier passing
checks grant no acceptance to a later source.

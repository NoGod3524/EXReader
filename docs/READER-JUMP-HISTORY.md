# Reader jump history (J07)

A bounded, host-reusable back/forward stack of reading positions for the reader
product. It stores real captured positions of the original book, in memory only.
It never stores an SDK handle, never resolves an anchor, never navigates and
never writes reading progress, an SDK note, a product revision or a catalog row.

- Fixed implementation start: `f43baf9182d75907c0cb5d6f77048f27bca8c950`
- Frozen SDK: `9854061be331fe603a1822d9b2b36ee357154927` (3.40.0, ABI 1)
- Product schema 1, wire v1 and reading anchor v1/v2 are unchanged; there is no
  new sync entity and no new database.
- Package: `apps/reader/jump-history` (EXReaderJumpHistory 0.1.0, C ABI, installed
  as its own CMake package). Only public installed packages are linked:
  EXReaderReadingState 0.1.0, and through it EXReader 3.40.0 and EXReaderRevisions
  0.3.0. No SDK private header, archive or second SQLite build is used.

## Public contract

`include/reader_jump_history.h` is the complete surface.

| Call | Meaning |
| --- | --- |
| `reader_jh_open(limits,out,error)` | Empty history. `limits` may be NULL (64 entries, 256 KiB). |
| `reader_jh_close(&h,error)` | Frees on the owner thread; on error the handle stays valid. |
| `reader_jh_adopt_thread(h,error)` | Hands ownership to the calling thread. |
| `reader_jh_clear(h,error)` | Drops every entry, keeps the limits. No-op when empty. |
| `reader_jh_commit(h,store,position,result,error)` | Encodes with `reader_rs_encode_v2` (validates, never inserts) and records the landing. |
| `reader_jh_commit_wire(h,store,kind,wire,bytes,result,error)` | Same rules for a wire the host already encoded. |
| `reader_jh_peek(h,direction,item,error)` | Neighbour in one direction without moving the cursor. `EMPTY` when none. |
| `reader_jh_item_at(h,index,item,error)` | Any entry by index, without moving the cursor. |
| `reader_jh_complete(h,item,error)` | Moves the cursor onto a peeked entry after the host has navigated to a FOUND resolve. |
| `reader_jh_item_release(&item)` | Releases `item.wire` and zeroes the item. |
| `reader_jh_state_get(h,state,error)` | Count, cursor, accounted bytes, limits, can_back/can_forward, generation, totals. |

### What an entry is

One entry is the exact reading-state wire that the **installed** revision
validator accepted - a `progress` `put` with a location, anchor version 1 or 2 -
plus a private canonical location key derived from the decoded wire.

A reading position is a **point**, not a selection: the installed validator
refuses a progress record whose quote is non-empty ("Progress requires a point
selector"), so every stored landing has `start == end`, an empty quote and the
SDK's 32-scalar prefix/suffix context. A host that tries to store a highlight
range gets `READER_JH_REVISION` and an untouched history - that is a property of
the shared wire, not of this component, and the cloud consumer proves it. The key
covers mode, `book_key`, `part_path`, the EPUB spine index, `page_id`, page, start/end and the
quote/prefix/suffix bytes. It deliberately excludes the transient revision ID,
the parser version and the anchor version, so two captures of one place compare
equal while a repeated spine path stays a distinct place because the index is
part of the key.

The wire carries a transient revision ID that is never inserted; it is a
position record, not a product revision. Nothing may treat that ID as existing
history.

### Classification, coalescing and truncation

The caller classifies every landing (`READER_JH_PAGE`, `READER_JH_SEARCH`,
`READER_JH_TOC`); the component never infers it.

Rules, in order:

1. same book and same location as the current entry -> `READER_JH_UNCHANGED`, nothing
   moves, the entry ID is the current one.
2. a `PAGE` landing after a `PAGE` entry of the same book -> `READER_JH_COALESCED`: the
   current entry is replaced, so a page turn is one landing and not two.
3. anything else is appended - including a place that already appears earlier in
   the history; a re-visit is a new entry, not a cursor move.

Every change drops all forward entries (`result.truncated`), then evicts the oldest
entries until both the entry count and the byte budget hold (`result.evicted`). The
newest entry is never evicted. `generation` increments on every change.

### Return protocol (host side)

`peek` returns a decoded copy, not a navigation:

1. `reader_jh_peek` -> `reader_jh_item` with `book_key`, `entry_id`, `generation` and `wire`.
2. The host decodes `item.wire` with `reader_rs_decode` (its own revision store).
3. The host reloads the book named by `book_key` with its own SDK owner and calls
   `reader_rs_resolve_reflow`, `reader_rs_epub_record_part` + `reader_rs_resolve_epub` or
   `reader_rs_fixed_page` + `reader_rs_resolve_fixed`.
4. Only on `FOUND` does the host navigate and then call `reader_jh_complete`.

`AMBIGUOUS`, `MISSING`, `LEGACY` and a refused route are never turned into a move: the
host simply does not complete. Not calling `reader_jh_complete` **is** the
cancellation - no cursor move, no generation change. If anything changed the
history after the peek, `reader_jh_complete` returns `READER_JH_STALE` and moves
nothing.

### Memory ownership

- `item.wire` is owned by the item and stays valid until `reader_jh_item_release`,
  independent of the history and of every SDK object that produced the capture.
  It survives `reader_jh_clear`, `reader_jh_close` and the release of the source
  document/fixed text.
- The out structures are zeroed on entry, so a caller reusing a
  `reader_jh_item` must release it first; reusing it without releasing loses the
  previous wire.
- The `reader_revisions *` handed to a call is borrowed for that call only.

### Threads and reentrancy

A handle belongs to the thread that opened it. Every call from another thread
fails with `READER_JH_THREAD` before any state is read or changed, including
`reader_jh_close`. `reader_jh_adopt_thread` transfers ownership; the host must then
guarantee the previous thread has stopped using the handle. Handles are not
synchronized. No call invokes a callback, so a call cannot reenter the handle.

### Errors and atomicity

`reader_jh_status` distinguishes argument, memory, unknown struct version, limit,
thread, revision, not-representable, too-large, empty and stale. `reader_jh_error`
adds the reading-state status/gap, the revision module status and a fixed
message that never contains a supplied path or secret.

Every error return leaves the history exactly as before: same count, cursor,
accounted bytes, generation and totals. `NOT_REPRESENTABLE`, `REVISION`,
`TOO_LARGE`, `ARGUMENT` and `THREAD` never store or drop anything.

### Limits

| Limit | Value |
| --- | --- |
| entries | default 64, hard cap 256, `0` selects the default |
| accounted bytes | default 262144, floor 4096, hard cap 1048576 |
| one entry | 32768 accounted bytes (wire + book key + canonical key) |

Accounting is `book_key + canonical location key + wire` per entry. A request outside
the caps is `READER_JH_LIMIT`; it is never clamped silently. An entry above the
per-entry cap, or above the byte budget, is `READER_JH_TOO_LARGE`.

Because a legitimate entry is bounded (68-byte book key, at most a 1024-byte EPUB
part path, 32-scalar context and its wire), one real position cannot exceed the
4 KiB byte floor on its own. The budget is therefore proven by eviction, and the
per-entry cap directly through `reader_jh_commit_wire`.

### What the component never does

- no SDK resolve, no navigation, no view change;
- no reading progress write, no SDK note write, no `reader_revision_local` insert,
  no catalog write, no new table or file;
- no persistence: the stack is bounded memory, so nothing is promised across a
  restart, a device or a sync session;
- no inference: an ambiguous target is never reported as found.

The cloud consumer proves the first two points by encoding and decoding through
the installed validator, then comparing the product revision rows, the outbox,
the SDK progress/note counts and the byte fingerprint of both databases before
and after the whole run, with a deliberate public write as the sensitivity
control.

## Building and consuming

```
cmake -S apps/reader/jump-history -B build/jh-package -G Ninja   -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="<prefix>;<sdk-stage>"   -DCMAKE_INSTALL_PREFIX="<prefix>"
```

Consumer:

```cmake
find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)
target_link_libraries(app PRIVATE EXReaderJumpHistory::reader_jump_history)
```

`tests/reader_jump_history/consumer` is the installed example: `probe.cpp` is a
C++ consumer that captures for real from TXT, EPUB, PDF and CBZ, and `api.c` is
a C consumer that shows the header is C-clean and the C ABI links.

## Cloud verification

`.github/workflows/reader-jump-history.yml` runs on ubuntu-22.04, windows-2022 and
macos-15. Each job:

1. guards `HEAD == GITHUB_SHA`, the fixed start as an ancestor, the eight protected
   SDK paths, product schema 1 and the shared reader modules, and rejects any
   changed path outside the J07 ownership list;
2. installs the product provider, the unchanged revision module, the frozen
   reading-library SDK and the reading-state adapter, then builds and installs
   this package from installed packages only;
3. compiles the C and C++ consumers against the installed package;
4. generates four deterministic originals, runs the consumers and judges named
   outcomes only (never a bare exit code);
5. preserves originals, logs, evidence and failures as one artifact per
   platform.

The `evidence` job downloads the three same-run ZIPs through the GitHub API in
Actions, re-computes their size and SHA-256, rebinds each summary and report to
this source/run/attempt, checks that the uploaded probe binary is the one the
summary hashed, and requires the three runners to agree on originals, case IDs,
lifecycle steps and the no-write proof.

Nothing here runs on a developer machine: no local compiler, generator, parser
or download.

## Verification status

`docs/validation/reader-jump-history.json` records the accepted run
`40125391353` (attempt 1) on tested source `4ff8c803`. ubuntu-22.04,
windows-2022 and macos-15 each built the package and the consumers from installed
packages only and ran 139 named checks with zero failures, five stored-wire cases
and five back/forward moves, and the runners agree on originals, case IDs,
lifecycle steps and the no-write verdict. The `evidence` job re-authenticated all
three same-run ZIPs inside Actions and kept that record as its own artifact.
`host_wiring_accepted` stays false: the four production hosts are wired by root.

Three earlier runs failed for real reasons and are retained in the record: a
zeroed item's status, a fixed-page progress query and an install path; the shared
wire refusing a selection as a reading position; and a cross-runner comparison
that embedded each runner's own path. Nothing here runs on a developer machine.

## Uncovered

- Host wiring, UI controls, menus and shortcuts in the four production hosts.
- Persistence, restart behaviour, cross-device and any sync entity.
- Dependence on other J packages or on the unmerged G03/G04 search/TOC hosts.
- Real user libraries, private cloud storage and real accounts.
- Latency/CPU budgets: only the documented entry and byte caps are enforced.
# Root 复审接续

从原交回 `496b426219d8b9ff50329c4a3a0336ae742acd94` 独立建立 `codex/reader-jump-history-review`，原 owner 工作树不改。源码复审发现两个缺陷：每个 history 从1开始的 entry ID 会让另一实例的 peek 在 generation/index 相同时被接纳；编码 wire 转入 `std::string` 时若分配抛错，原 `reader_rs_free` 无法执行。

修复以进程内不复用的原子 entry ticket 约束完成操作，不改公开结构或 wire；内存耗尽路径用原释放器的 RAII 托管。新增相同位置、不同位置、关闭后重建三种实例混用检查，拒绝后核 state 不变且自己的 ticket 仍能使用。旧139项、四格式、无写入控制和三平台安装消费者保留。

当前修复尚待 Actions 验证，原 run `40125391353` 的通过仍只归原 source `4ff8c803faec4d4bb351175290ad9f1cb9b82938`，不能转授当前候选。

首个修复 source `1902a41bc9bb1c8b0dc7dcbd608d915f1948d669` / run `40153658637` 已三平台与 strict 全绿。继续补齐原汇总遗漏的上游作业身份认证：必须三个同源码同 attempt 的 completed/success 作业，并从 ZIP 原始报告重新核具名结果，不能仅依赖报告摘要。新增12个作业/运行身份负例仅在 Actions 执行；该汇总强化版本需新源码完整验证。

强化 source `910aa03ef3e6cc45f2f5e065f2ea01e300f27a70` / run `40153976517` 三平台消费者仍通过，但 strict 真实拒绝原探针重复命名的通用检查。现保留每一次原断言，仅给同名检查的第二次及以后加稳定序号；没有降低去重要求。另增6个原始结果负例，与12个身份负例合计18个，等待新同源整轮。


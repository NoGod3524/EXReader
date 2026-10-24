# EXReaderLocalDownloads 0.1.0

Optional C ABI package that removes **only the local original and the local SDK
mapping** of a downloaded book. The global product book, shelves/tags/series,
revision history, outbox and every remote object are never read or written, and
no deletion tombstone is created. It is not part of the default reading build;
it links only installed public packages (`EXReader` library, `EXReaderSideload`,
`EXReaderProductCatalog`) and reads no private SDK SQL.

Interface: `reader_local_downloads.h`, target `EXReaderLocalDownloads::reader_local_downloads`.

| Call | Purpose |
| --- | --- |
| `reader_ld_remove` | Remove the local copy of `format:sha256`. Cloud-only keys and repeated requests succeed with `already_cloud`. |
| `reader_ld_recover` | Finish or roll back the single pending intent. Idempotent. |
| `reader_ld_pending` | Read-only inspection of the intent; touches neither database. |
| `reader_ld_reimport` | Attach a downloaded file again; it must match the original format and SHA-256. |

## Calling contract

* Run on the thread that owns the `exr_library` and the `reader_catalog`.
* Release every `exr_source`/reader opened on the book and stop network tasks that
  touch the original **before** calling. Report anything still in use through
  `is_busy`; the call then returns `busy` and changes nothing. Deleting an SDK row
  permanently invalidates sources previously opened on it (SDK contract).
* A rejected or failed call leaves the SDK rows, the mapping and all metadata
  readable, so a source opened before a refused call stays valid.
* Use a state directory that only this module writes to. No thread or network is created.

## Durable intent

There is no cross-database transaction, so the module writes
`state_dir/intent.rdi` (temp file, flush, atomic replace, SHA-256 checked) and
advances it only after the previous step verifiably finished:

| Stage | Meaning | Recovery |
| --- | --- | --- |
| `begun` | request recorded, nothing destructive done | roll back (clear exports, drop intent) |
| `prepared` | identity proven by a verified export; byte-identical SDK copies and legacy data known | roll back while the mapping exists; if the mapping is already gone, roll forward |
| `unmapped` | local mapping removed, SDK rows still hold bytes | roll forward |
| `deleted` | verified SDK rows deleted | roll forward (remove export, intent) |

Every step is idempotent, so a kill between a step and its stage write is harmless.
A second removal or a re-import is refused with `pending` while an intent exists.

## Identity and duplicates

The mapped SDK row must have the key's format, and its exported original must have
exactly the key's size and SHA-256, or the call fails with `identity` and changes
nothing. Ordinary SDK imports may create several rows with identical bytes; every
row is accepted into the removal set only after its own size and SHA-256 match
(at most 8). Rows with the same title but other bytes are never touched. Before
each delete the row is verified again; a row that no longer matches is skipped
and counted in `copies_skipped`.

## Legacy SDK-only notes and progress

Notes and reading progress stored only in the SDK are never dropped silently, and
no product revision is assumed to cover them. The default policy `reject`
returns `legacy_data` (with note/progress counts) before any change. The
`backup` policy first writes a verified `exr_library_backup` copy
(`state_dir/legacy/<sha>-<n>.exrbackup`, never overwritten, never deleted by this
module; it holds the whole SDK library, so it can be large) and then removes the
original. If such data appears between a crash and recovery, recovery with
`reject` puts the mapping back (`restored`) and keeps every row.

## Re-download

`reader_ld_reimport` checks the file's size and SHA-256 against the key, imports
it with `exr_sideload_import_file`, and attaches it with the stored product
metadata, so the identity stays format + original SHA-256. A new SDK row ID is
normal; IDs are never wire identities.

## Validation

`.github/workflows/reader-local-downloads.yml` builds the frozen SDK, sideload
and catalog packages, installs this module, and judges it through independent C
and C++ consumers on Windows, Linux and macOS. The probe terminates itself with
`_exit` inside the durable-stage hook at each of `begun`, `prepared`, `unmapped`,
`deleted` and `cleaned`; fresh processes then reopen and recover. Python reads the
product database independently and compares reader tables, revisions, tombstones,
outbox and a simulated remote object tree before and after each case.
`docs/validation/reader-local-downloads.json` records only what a same
source/run/attempt actually granted; nothing here is granted until it says so.

Not covered: UI/host wiring (owned elsewhere), real devices, large-library
backup cost, PDF fixtures, and any sync protocol. The module designs none.

## 审查回修（第 1 轮，root 源码审查）

本轮在不改 SDK、产品 schema、wire 和既有断言的前提下，按 root 的五项发现改实现并补确定性回归；
原有 31 个具名检查全部保留，新增 20 个具名检查（共 51）。

### 1. 重导入身份 TOCTOU

旧实现先 `ld_hash_file(path)`（关闭文件），再 `exr_sideload_import_file(path)`，最后**不核对
SDK 实际保存的字节**就把返回值映射到旧 `book_key`。取消回调在已读 buffer 之后把 pathname 换成
另一个同格式、同尺寸的有效原件即可让"哈希算 A、导入 B"。

现在：`ld_stage_copy` 用**一个**已打开句柄把调用者文件复制到私有
`originals/<sha>.open`（独占创建），同时对该字节流做 SHA-256；尺寸/摘要与该书身份不符即拒绝并删除
暂存；导入只读这份私有副本；导入后再用公共 `exr_library_source` **重新哈希新行**，与身份不符则删除
该行、不写任何映射。PDF 的已验证副本保留为 `originals/<sha>.orig`（定页读取依赖该私有文件），
只在该书再次移除时删除；其他格式立即删除暂存。

回归：`check_regressions.py` 用**同一份探针源码**分别链接**上一受测实现**（`7817caa9`）与本树，
证明旧实现存入的是替换后的字节（`stored_matches_identity=false`），本树保持原字节（`true`）；
`reimport_path_swap_keeps_identity`、`reimport_verifies_imported_row`、`pdf_private_original` 在
三平台消费者上验证同一性质。

### 2. intent 记录解析

旧读取只 `fread` 2048 字节、不验证 EOF，且用 `atoi`/`strtoull`/`strtok`：数字后缀、重复字段、
未知字段、超过 2048 字节但前 2048 字节自洽的文件都会被接受。现在改为严格有界解析：必须精确到文件末尾、
字段集合与顺序固定、每个字段只出现一次、数字必须是纯十进制（无符号/后缀/溢出/空元素），ids 1..8 且
必须包含 mapped，校验和覆盖全部前序字节。任何不符都返回 `CORRUPT_INTENT`，**原文件与两个数据库逐字
不变**（回归逐例比较 sdk.db / catalog.db 摘要与 intent 文件摘要）。

回归：`intent_trailing_bytes`、`intent_trailing_nul`、`intent_oversized`、`intent_truncated`、
`intent_bad_number`、`intent_stage_suffix`、`intent_duplicate_field`、`intent_unknown_field`、
`intent_empty_id`、`intent_nine_ids`；`check_regressions.py` 进一步证明旧实现对
`stage=2junk`、`bytes=<n>abc`、重复 `bytes=`、未知字段、溢出 id、以及"前 2048 字节自洽 + 尾随字节"
这六种记录返回 `ok`，本树返回 `corrupt_intent`。

### 3. 状态目录与临时文件边界

`ld_is_dir` 现在不跟随链接（POSIX `lstat`；Windows 额外拒绝 `FILE_ATTRIBUTE_REPARSE_POINT`），
因此目录符号链接/junction 会被拒绝而不是被"沿着清理"；`ld_create_exclusive`（`O_CREAT|O_EXCL|
O_NOFOLLOW` / `CREATE_NEW`）配合先删除目标项，保证预置的同名文件、硬链接或 reparse 点不会被截断；
清理改为**按书删除自己的两个文件名**（`<sha>.orig`、`<sha>.open`），不再清空整个目录——另一本书
仍在使用的私有原件不会被下一次移除清掉。

回归：`state_dir_link_refused`、`originals_link_refused`（cache 外 sentinel 逐字不变、目录内容不变）、
`intent_tmp_hardlink_kept`（预置硬链接的 sentinel 不被截断）。

### 4. 回调重入

`after_stage`/`is_busy`/取消回调若再次调用 `reader_ld_remove`/`recover`/`reimport`，现在返回
`READER_LD_BUSY` 且不改动任何持久状态；外层调用继续完成并可恢复。`reader_ld_pending` 明确为只读，
允许在回调内调用，并报告已提交的阶段。

回归：`reenter_remove_from_stage`、`reenter_recover_from_busy`、`reenter_pending_readonly`。

### 5. 九格式覆盖

`formats_all_remove_reimport` 对 txt/html/fb2/epub/docx/rtf/mobi/**pdf**/cbz 逐一执行
"移除 → 全局书目保留、本机映射消失、SDK 行删除、无残留导出" 与 "按原格式+原始 SHA-256 重导入 →
字节与映射精确恢复"，再移除并核对其邻居可读；PDF 另有 `pdf_private_original` 覆盖私有原件寿命与
跨书清理隔离（真实公共 SDK 原件为 `tests/fixtures/pdf-public.pdf`）。

## 云端结果（同一次 source/run/attempt）

受测源码 `44a6991f65021b58f48165124fd5ae654b14e157`，run **40086428132**，attempt **1**，
四个作业全部 success；逐项明细、消费者 SHA-256 与工件身份见
[`docs/validation/reader-local-downloads.json`](validation/reader-local-downloads.json)。

| 宿主 | 具名检查 | 跳过 | 消费者 probe SHA-256（前 12 位） | 回归（旧实现 vs 本树） |
| --- | --- | --- | --- | --- |
| ubuntu-22.04 | 51/51 | 0 | `292a67fdcc36` | swap old=False / new=True，6 项解析缺口 old=ok → new=corrupt_intent |
| macos-15 | 51/51 | 0 | `5cd5ff8b48c4` | 同上 |
| windows-2022 | 51/51 | 1 | `8f6f26265b39` | 同上；swap 用例按主机限制**具名跳过** |

Windows 的跳过是诚实的平台事实：该宿主拒绝替换本进程正在读取的文件
（`SWAP blocked errno=13`），所以"哈希后替换 pathname"在该平台无法发生；同一身份性质在
Windows 上仍由 `reimport_verifies_imported_row`、`reimport_wrong_file_rejected` 与导入后重读校验覆盖。
Linux/macOS 上该用例是**通过**（旧实现存入替换后的字节，本树保持原字节）。

工件：Windows `12557321439 / 10658927 B / feaaecc2…`、Linux `12556894780 / 13947926 B / 832723ef…`、
macOS `12557352053 / 12178196 B / e6796868…`、证据 `12557301558 / 3089 B / 27667855…`，均 2027-01-22 到期。

### 本轮早期失败（保留，不转为通过）

| run | 源码 | 原因 | 处置 |
| --- | --- | --- | --- |
| 40083596698 | `368eebf0` | ubuntu -Werror=format-truncation（intent key 拷贝）；三处新检查缺陷 | 加长度校验后 memcpy；修检查 |
| 40084663610 | `8eb1b6b5` | 两处新检查缺陷（same() 少参数；PDF 场景误要求 originals 为空） | 修检查 |
| 40085199662 | `2c35eba4` | Linux/macOS 全绿；Windows 拒绝替换打开的文件，swap 用例判失败 | 改为具名跳过并说明原因 |
| 40085621462 / 40086062994 | `32031918` / `5976fca7` | 全部作业绿；swap 行按全等匹配把通过误报为跳过 | 改为前缀匹配后重跑 |

通过证据只取上表那一次 source/run/attempt；早期 run 的结果不拼接到当前源码。

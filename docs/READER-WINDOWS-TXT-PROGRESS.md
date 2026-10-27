# Windows TXT 阅读位置：产品内容身份与规范化文本位置

原始位置模块从有界 TXT 阅读路径出发；当前组合候选同时包含字号重排、
小 TXT 兼容路径和经授权的新 SDK 候选。冻结版本和历史证据保持独立。

## 为什么不能用 SDK 书籍身份

本包的大 TXT 路径使用产品原件，而非 SDK 本机书号：宿主走
`reader_original_import` 把不可变原件存入产品目录，书架行以
`format:sha256` 为身份、`sdk_book_id` 为 0。旧 SDK 的内存导入接口支持 TXT，
但需要完整解析并受既有资源上限约束；本路径为大文件使用有界 pager。
该路径的进度使用：

- **产品内容身份** `txt:<原文字节 SHA-256>`（与产品目录同一身份，跨设备稳定，不含本机行号）；
- **规范化文本位置**：TXT pager 自己给出的整篇投影 UTF-8 字节偏移（页首偏移），
  不是页码。布局/字号改变后按同一内容偏移重新定位；
- **真实捕获的上下文窗口**：保存点处最多 32 个标量 / 128 字节的投影原文，
  作为 wire v2 `selector.prefix/suffix`，恢复时逐字节核对。

wire 仍是既有阅读位置 v1 封装中的 **anchor_version 2 点选择器**
（`reflow_global`、`exact=""`、`start==end`、`chapter=null`），由既有
`EXReaderRevisions` 校验后写入 `reader_revisions` + `reader_outbox`。没有新实体、
新表、新字段，也没有页码参与持久定位。

## 模块（`apps/reader/txt-progress`，`EXReaderTxtProgress 0.1.0`）

公开 C 头 `reader_txt_progress.h`，C++17 实现，只用已安装的
`EXReaderRevisions` / `EXReaderReadingState` / `EXReaderReadingCommands` /
`EXReaderCommands`，不链接 SDK 私有档案，不打开 SDK 书库。

| 入口 | 语义 |
| --- | --- |
| `reader_txp_open/close` | 一个 schema1 产品库连接，由调用方工作线程独占；显式 raw 能力与构建族一致，否则 `ARGUMENT` |
| `reader_txp_capture` | 把捕获窗口裁剪到 32 标量 / 128 字节的 UTF-8 边界；NUL 与非法 UTF-8 拒绝（不转义、不静默截断） |
| `reader_txp_ensure_book` | 幂等的产品书籍身份：已存在则永不重写，原文字节数不符即 `IDENTITY` |
| `reader_txp_save` | 观察完整头集后写一份 v2 点修订；位置未变则不写（`unchanged=1`） |
| `reader_txp_load` | 只取唯一完整安全头；`MISSING/CONFLICT/PENDING/BLOCKED/LEGACY` 明确返回 |
| `reader_txp_match` | 已保存窗口与当前投影窗口逐字节比对；窗口未覆盖该点返回 `ARGUMENT`，不当作匹配 |

### 冲突、多头与旧数据

- **并发头**（`READER_SELECTION_CONCURRENT`）：返回 `CONFLICT`，不选择、不覆盖、不写；
  其他设备的头全部保留。
- **缺父 / 需要显式恢复**：`PENDING` / `BLOCKED`，同样不写。
- **观察头集合被别的写入改变**：底层事务以 `UNSAFE` 拒绝，本模块透传，历史不变。
- **旧 anchor v1 记录**（带引文的旧进度）：`load` 返回 `LEGACY`，本机不据此跳转、
  不重写；用户继续阅读时可以写入以该 v1 记录为父的 v2 点，旧字节永久保留在历史里。
- **历史上限**：每个实体 4096 份，达到后返回 `LIMIT`，已保留的头不变。

## 宿主接线（`examples/reader.c`，`EXR_READER_WINDOWS_TXT_PROGRESS`）

- `job_open_txt`：建立 pager 后先恢复——读安全头、核对捕获窗口、按偏移二分定位页，
  再接受该页；无历史时从第一页开始并允许首次保存。`LEGACY/CONFLICT/…` 或核对不一致时从第一页开始并置
  `hold_progress`，且给出明确状态，**不覆盖**任何既有记录。
- `save_txt_progress`：把已接受页的首偏移 + 上下文交给 `JOB_TXT_PROGRESS`，
  在工作线程写产品修订；未移动一个 32 KiB 块且没有强制请求时不写。
- 强制写：关窗（`finish_close`）、切换书目、字号重排。写入被拒时关窗仍然完成，
  已保留记录不变（`txt_save_abandoned`），避免窗口关不掉。
- 字号：TXT 走 `JOB_LAYOUT` 的新 pager（复制同一源句柄），按内容偏移重排并接受该页。
- 有界大 TXT 的搜索、注记、选择、跳末页仍报告“尚未实现”。

原始位置模块的宿主接线包括：`page_for_offset` 允许 TXT 的 EOF/范围语义，
`save_progress` 把 TXT 会话分流到产品写入器。翻页路径（`job_txt_go`、`txt_frame`）
在原始位置模块中未改动；当前组合另包含翻页和重排修复。

## 验收（Actions，真实 Windows 宿主）

`tests/reader_txt_progress/build.py`：SDK → 产品 SQLite provider → revisions →
commands → reading-state → reading-commands → txt-progress 全部安装后，用独立安装
消费者跑 16 项探针，并由 `check.py` 直接核对留存数据库（修订数、outbox、
并发头、v1 原始字节、v2 点无引文）。

`tests/windows_host/txt/check_progress.py`：真实 `EXReaderProduct.exe` 覆盖
16,792,975 字节原件的选书、六次向后翻页、字号变化、关窗重启恢复、
第二本书身份隔离、产品库写锁下的拒绝写入（记录不变、仍能退出、重启后仍恢复旧位置），
以及既有 SDK 固定页书籍回归。

## 已知限制

- 位置写入按 32 KiB 内容位移节流，未到阈值且未触发强制写时崩溃会丢失该区间内的移动；
  正常关窗、切换书目、字号变化都强制写入。
- 恢复不确定（核对不一致/旧记录/并发头）时会话内不再自动写入，避免用第一页覆盖旧记录。
- 页面文本上限、1 MiB 修订上限、4096 份实体历史沿用既有约束。
- 有界大 TXT 的书签、注记、搜索、文字选择、末页跳转/页内链接等仍未实现。
- 与主协调者翻页优化的合入：本包只改 `page_for_offset` 的两处判断和宿主会话字段，
  合入时需以对方 `job_txt_go`/`txt_frame` 为准，冲突点已隔离在
  `#ifdef EXR_READER_WINDOWS_TXT_PROGRESS` 内。

## 状态

Windows uses the existing SDK import and reading path for TXT files up to 16 MiB,
preserving notes and reading records. Larger TXT originals use the bounded
pager and product-content position described above.

- Standalone source `f9c0270941f5bc26f16bfa26281f50cc2a6a29cb`:
  [Actions 40539084634](https://github.com/NoGod3524/EXReader/actions/runs/40539084634)
  passed its native Windows position checks and all four Windows/Linux module jobs.
- Composed source `a7020b07b8515e0d4b8e2693522920e2ec78eb35`:
  [Actions 40541383239](https://github.com/NoGod3524/EXReader/actions/runs/40541383239)
  passed native TXT progress, retained compact UI and extracted native UI.
- These results describe the exact sources named above. The current combined
  source requires its own Actions acceptance. Physical devices, performance
  targets and unsupported bounded-TXT features are not granted by these runs.

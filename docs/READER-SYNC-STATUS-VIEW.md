# 同步与待处理状态只读视图

`apps/reader/sync-status-view` 是可选安装包 `EXReaderSyncView 0.1.0`，复用
`EXReaderSession 0.1.0` 及其公开的 `reader_revisions` 接口。它只读：不写产品库、
不发网络请求、不新建线程、不启动/取消同步、不自动重试、不 ack。默认 reading 构建
不加入它，宿主面板接线由 root 统一完成。

## 公开接口

```c
reader_sync_view_status reader_sync_view_capture(reader_session *, reader_revisions *,
    const reader_sync_view_options *, reader_sync_view_snapshot **out, reader_sync_view_error *);
reader_sync_view_status reader_sync_view_summary_get(const reader_sync_view_snapshot *, reader_sync_view_summary *);
reader_sync_view_status reader_sync_view_rows(const reader_sync_view_snapshot *, size_t offset,
    reader_sync_view_row *rows, size_t capacity, size_t *copied);
reader_sync_view_status reader_sync_view_release(reader_sync_view_snapshot **);
const char *reader_sync_view_phase_text(reader_sync_view_phase);
const char *reader_sync_view_reason_text(reader_sync_view_reason);
```

- **输入**：`session` 必填；`revisions` 可为 NULL（只看会话）；`options` 可为 NULL
  （100 行、不做冲突探测）。`row_limit` 0 表示 100，硬上限 100；超过返回
  `READER_SYNC_VIEW_ARGUMENT`。
- **输出与内存归属**：成功时 `*out` 指向新快照，快照自持全部内存、不借用句柄或模块
  文本；调用方用 `reader_sync_view_release` 释放且只释放一次。失败时 `*out` 恒为
  NULL，不保留任何内存。`release(&NULL)` 与重复释放同一指针都返回 OK。
- **寿命**：快照在会话被 destroy、revisions 被 close 之后仍然有效；`summary_get` 与
  `rows` 只读快照，可任意线程并发读取，直到 release。不要在另一线程读取同一快照时
  release。
- **读取序列**：一次 `reader_session_observe`（互斥保护的整份拷贝）→ 一次
  `reader_revision_outbox` 页（最多 `row_limit` 行，先整页拷贝再做别的调用）→ 最多
  `row_limit` 次 `reader_revision_heads`。这是**分开的读**，不是事务：每一步自身
  一致，后台 worker 可以在两步之间推进。
- **线程/重入**：带 `revisions` 时必须在打开它的线程调用，且不能在其回调里调用；
  `reader_revisions` 拒绝这种重入，本模块随之返回 `READER_SYNC_VIEW_REVISIONS` 且
  `revision_code = READER_REV_OWNER`、`*out` 为 NULL。`revisions` 为 NULL 时除
  会话互斥与 SQLite busy 等待外不阻塞，任意线程可调用。
- **错误**：`READER_SYNC_VIEW_ARGUMENT`（参数/上限）、`_MEMORY`、`_SESSION`
  （`reader_session_observe` 失败）、`_REVISIONS`（outbox 或 heads 读失败，
  含 owner 违规）。冲突探测读失败会让整次 capture 失败，而不是报告"无冲突"。
  `reader_sync_view_error.message` 是固定模块文本，不含 URL、凭据、路径、标题或
  服务端正文。
- **取消**：capture 本身不可取消也不需要取消——工作量已被 `row_limit` 与 heads
  上限界定（≤100 行、≤100 次 heads，每次 heads 本身受 4096 修订限制）。取消正在跑的
  sweep 仍是 `reader_session_cancel` 的职责。
- **提交边界**：capture 没有任何写操作，不构成产品事务；它不是 ack/retry 的依据。
- **硬上限**：`READER_SYNC_VIEW_MAX_ROWS = 100`、`READER_SYNC_VIEW_SHARD_COUNT = 256`。

## 语义

`phase` 一一对应 `reader_session_state`：idle / syncing / cancelling / cancelled /
sweep-complete / failed / closing / closed，外加 unknown。

- `sweep_complete` 表示**一次** 256 分片扫描走到 255 分片结束；`library_complete`
  恒为 0（复制会话自己的标志）。"全书库完成"不是本模块能给出的结论。
- `operations`、`pushed_operations`、`pulled_operations`、
  `originals_verified_operations`、`metadata_wait_observations`、
  `original_wait_observations` 是**操作/逐步骤观测次数**，重试或失败的步骤可能把
  同一条记录再计一次。
- `pending_records`、`retried_records`、`conflict_records` 是本次列出的**不同
  记录数**（outbox 页内），不是剩余总量，也不是操作次数。outbox 没有总数或游标
  接口：`more_may_exist` 只表示这一页填满了 `row_limit`。ack/retry 之后需要重新
  capture。
- `resumable` 在 cancelled/failed 为 1：下一次 start 从保留的 `cursor` 继续。
- `reason` 只来自模块状态码：needs-credentials / offline / tls / server / account /
  storage / conflict / integrity / limit / internal / none。取消不算错误（none）。
- 行只暴露固定 token 与 ID：`revision_id`、`entity_kind`、`operation`、
  `bytes`、`attempts`、`last_revision_code`/`last_reason`、`conflict`；
  不带 entity key、标题、URL 或原文引用。`last_reason` 由
  `reader_revision_retry` 写入的 `revision_error_<code>` token 解析，其它文本一律
  视为无原因。

## 云端出口

`.github/workflows/reader-sync-status-view.yml`：Linux/Windows/macOS 三平台，
从安装前缀编译实际 C 与 C++ 消费者（`status-view-c-consumer`、
`status-view-consumer`），对真实原生 TLS 会话执行完整状态转移、256 分片、部分提交、
离线/401/重试/取消/关闭、outbox 分页与 owner 重入、快照寿命、计数对照、存储不变、
秘密扫描，并由 `tests/reader_sync_status_view/aggregate.py` 严格汇总同次工件
（重算 ZIP 摘要、核对 API digest/字节/有效期、报告身份与具名清单）。统一守卫：
`HEAD == GITHUB_SHA`、固定起点为祖先、SDK 保护树与产品 SQL 相等、diff 全在白名单。

## 未覆盖

- 本包不做宿主面板/UI 接线与产品集成（root 负责）。
- 待 metadata 的**正向真实路径**没有独立夹具（需要既有 reading 事务面）；只验证
  `metadata_wait_observations` 与 `reader_session_snapshot` 逐字段相等。
- 移动端（Android/iOS）真机与宿主音频/朗读、性能、无障碍范围分别登记，不由本包授予。

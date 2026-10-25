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


## 云端验收

受测源码 `d427875579f714c0874c1b3cc5388b95a7f4e950`（固定起点
`f43baf9182d75907c0cb5d6f77048f27bca8c950`），run `40124617915` attempt `1`。
Linux/Ubuntu 22.04、Windows Server 2022、macOS 14 三平台各以安装前缀编译实际 C 与 C++
消费者，对真实原生 TLS 会话跑完 22 项具名检查（22/22，全部 pass）；汇总作业在同一次
run/attempt 内逐个下载三份归档，重算 SHA-256 与 API digest 比对，从归档内重读
`result.json` 与消费者字节并核对 `source_sha`/run/attempt/platform/具名清单，缺项、
跨源码、跨 attempt 或摘要不符即失败。结果为 `problems: []`。

| 平台 | job | 工件 | 字节 | sha256 |
| --- | --- | --- | --- | --- |
| linux | 120963276896 | `reader-sync-status-view-Linux-40124617915-1`（12572950281） | 2808934 | `ad0a69713f02f3e35dcc9e341a92619e2f6f97f7c03ceb8b6cc1915b20356338` |
| win32 | 120963277062 | `reader-sync-status-view-Windows-40124617915-1`（12572069143） | 2495443 | `61737f60a44ab0835d3f412c4f72aaaf663e7b1e92159484cf4e516d282ce788` |
| darwin | 120963276635 | `reader-sync-status-view-macOS-40124617915-1`（12573315552） | 2418831 | `6227060374f9534966ef41edaebf7dd8759a9324be1100760de30f4960d14757` |
| 汇总 | 120965848353 | `reader-sync-status-view-aggregate-40124617915-1`（12573235566） | 7704671 | `8814d9b954ce18de6c26956a56d8edbb467b761b7fe25f7e8d136688b42d032d` |

四份工件均非空、未过期（`2027-01-22T19:17:29Z`）。完整身份、逐条报告与保留失败见
[状态视图验收](validation/reader-sync-status-view.json)。

## 保留的失败与候选

| 源码 | run | 结果及接续 |
| --- | --- | --- |
| `f52900ad` | `40122530644` | 两平台在配置 sync 时找不到 `EXReaderRevisions`：安装前缀只写进 `GITHUB_ENV`，同一步内不可见。改为每次 configure 显式 `-DCMAKE_PREFIX_PATH`。 |
| `58102433` | `40123173490` | Linux 在 `-Werror=misleading-indentation` 处失败；Windows 通过 4 项后断言"完成的分片仍保留非空游标"，而完成分片的游标本就为空。源码改为全括号控制流，夹具改为单分片 105 条。 |
| `4e0cb525` | `40123647670` | 源码两平台编译通过，但验收脚本仍是"每分片一条记录"的旧夹具，重蹈空游标断言；macOS 未启动即取消。 |
| `a78b7286` | `40123947125` | 续跑扫描阶段 `KeyError: completed_sweeps`：测试读取了消费者并未发布的汇总字段名。保留。 |
| `154b1d40` | `40124504199` | 修正字段名后取消，用于重新武装夹具放行闸；不作验收声明。 |

以上失败与工件保留，前轮通过项不授予后轮源码。本包只授予"Windows/Linux/macOS 安装后
只读同步状态视图模块与真实原生 TLS 会话"这一范围；宿主面板接线、待 metadata 正向路径、
移动端、音频/朗读、性能与无障碍分别登记。

## 未覆盖

- 本包不做宿主面板/UI 接线与产品集成（root 负责）。
- 待 metadata 的**正向真实路径**没有独立夹具（需要既有 reading 事务面）；只验证
  `metadata_wait_observations` 与 `reader_session_snapshot` 逐字段相等。
- 移动端（Android/iOS）真机与宿主音频/朗读、性能、无障碍范围分别登记，不由本包授予。
# Root 严格汇总修复候选

从原交回 HEAD `823bd01962432b70cd8f0728443fab95ca55404f` 独立建立 `codex/reader-sync-status-review`，模块实现不改。原汇总只列出jobs，未强制三个同源码同attempt的上游作业均completed/success；ZIP内多个结果或消费者会取最后一个匹配项。

现认证真实运行/workflow与三个明确上游作业，拒绝重复工件及重复ZIP成员，并要求恰有一份报告、一份真实消费者二进制。增加17个运行/作业/ZIP成员负例在Actions执行；原三平台22项真实TLS、256分片、取消/重试/凭据、存储不变及秘密扫描全部保留。当前候选待新同源整轮，旧source `d427875579f714c0874c1b3cc5388b95a7f4e950` / run `40124617915` 仅归原交回。

首轮 root source `3178736b4c4f30d54faffc759da55dddec0ad86b` / run `40154693490`：Linux、Windows通过；macOS实际四线程消费者统计 `ok=98/failed=0` 而拒绝，strict未执行。根因是探针多个线程无同步自增同一组普通整数，丢失成功计数；现每线程独占计数，join后在主线程归并，原4×25=100的严格断言不改，模块生产实现仍不变。失败运行与工件保留。

线程统计修正 source `4ba603437c0f4f7bedd166e09891bbeb14789820` / run `40154953728` 三平台22项及严格汇总全通过。复核原报告仍有 `metadata_wait_positive_covered=false`，原检查只比较零值。现用真实独立session播种缺少book metadata的progress删除修订，跑完整256分片，必须观察到正数pending-metadata、视图精确镜像并保留未确认outbox；strict要求该正例覆盖标记。模块实现不变，这一补齐版本仍需新同源整轮。

补齐首轮 `7b70faf6` / run `40156517005` 三平台均在新夹具播种时被原修订validator拒绝：progress删除也必须显式`location_kind=reflow_global`，原helper默认none。本次仅修夹具的既有公开契约字段，validator与实际pending正数断言保留，原失败不删。

`63506780` / run `40156837215` 已实际观察到正数pending-metadata且精确镜像，但新增Device未发送公开消费者的`open`命令，capture为session-only而没有outbox，行保留断言因此失败。补上该设备本线程的revisions打开/关闭，保留正数与未ack行的全部要求，继续新同源整轮。


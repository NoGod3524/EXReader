# G07 账号同步故障一致性专项（reader-sync-resilience）

固定实现起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，分支 `codex/reader-sync-resilience`。
本包是**测试包**：只新增独立消费者、受控故障服务与验收，不改 session / sync / revisions / WebDAV 实现。

## 1. 范围与不变项

新增（且仅新增）：

- `tests/reader_sync_resilience/**`：具名边界清单、阶段握手夹具、独立消费者、逐平台验收、跨平台严格汇总。
- `.github/workflows/reader-sync-resilience.yml`：Windows / Linux / macOS 三平台实际原生 HTTPS + 独立进程，外加一个同 source/run/attempt 的严格汇总作业。
- `docs/READER-SYNC-RESILIENCE.md`、`docs/validation/reader-sync-resilience.json`：本记录与持久证据。

不修改（工作流门禁逐字校验）：

- SDK 保护树 `K=9854061be331fe603a1822d9b2b36ee357154927`（`src/ include/ cmake/ CMakeLists.txt tests/fixtures bindings/` 及两个原工作流）。
- 产品 schema 1（`apps/reader/store/**`）、`apps/reader/session|sync|revisions`、`extras/webdav`、`extras/opds`。
- 其他 15 路、root、原有 owner 的分支与目录。共享缺陷按“最小复现 + 建议补丁”交 root，不在本包内私改。

复用（未改一行）：已安装的原生包 `EXReaderProductCatalog` / `EXReaderWebDAV` / `EXReaderRevisions` / `EXReaderSync` / `EXReaderSession` 公共 C/C++ API；
`tests/reader_revisions/consumer`（协议 owner 的公开 CLI）用于本地 revision 落库与 `heads`/`get` 回读；
线格式辅助 `tests/reader_sync/check_sync.py` 的 `raw` / `revision` 纯函数。

## 2. 独立消费者

`tests/reader_sync_resilience/consumer/main.cpp` → `resilience-consumer`，两种模式：

| 模式 | 参数 | 作用 |
| --- | --- | --- |
| `session` | URL PRODUCT CACHE ORIGINALS ACCOUNT TIMEOUT_MS | 控制行协议 `start/cancel/observe/close/destroy`；`abort` 按 `_Exit(7)` 直接离开（无析构、无 close、无 ack） |
| `step` | URL PRODUCT CACHE ORIGINALS SHARD AFTER LIMIT TIMEOUT_MS | 恰好一次 `reader_sync_step`，打印安装后的公开 report（含 `status/dav_code/revision_code/http_status`） |

`abort` 只存在于**本包新增的消费者**里，是宿主进程自身的退出选择；共享模块没有新增任何 test hook。

## 3. 阶段握手夹具

受控 WebDAV/TLS 服务跑在 IPv4 回环、证书带 `DNS:localhost,IP:127.0.0.1` SAN（三平台各自装入临时信任库）。每个请求进入 `requests` 轨迹（方法、路径、是否带凭据、`If-None-Match`、`Depth`、状态、阶段、PUT body SHA-256；**从不记录 Authorization 值**）。

可门控阶段（按 `(method, path)` 一次性消费）：

| 阶段 | 语义 | 用于 |
| --- | --- | --- |
| `before_body` | 收到 PUT 头但永不读 body | 上传未落盘时 kill |
| `after_commit_hold` | body 已落盘，响应被扣住 | PUT 已提交、客户端未 ack 时 kill |
| `before_response`（GET/PROPFIND） | 命中但响应未发出 | 验证 GET 前、ack 前、检出请求中退出 |
| `partial_body` | 发 Content-Length 全长但只发前缀后扣住 | 验证 GET / 原件下载中途 kill |
| `short_body_close` | 发一半后 RST | 截断响应不得被当作 ack 依据 |
| `reset_mid_body` | 读一半 body 后 RST | 上传断连 |
| `stall_before_headers` | 不回头、不回体 | 原生传输超时及有限等待回归 |
| 状态注入 | 401 / 403 / 429 / 503（可带 `Retry-After`） | 真实状态码 |

kill 一律是 `SIGKILL`（POSIX）/ `TerminateProcess`（Windows）；`abort` 是自我 `_Exit(7)`。每条 kill 边界都记录 `pid / termination / returncode`。

## 4. 21 条新增具名边界

每条都记录 `expected`（不变量文字）与 `actual`（实测字典：退出身份、outbox/history 计数、远端与本地 SHA-256、PUT 结果序列等）。

| # | 边界 id | 阶段 | 期望不变量 |
| --- | --- | --- | --- |
| 1 | `put_committed_before_ack_response_withheld_then_kill_preserves_remote_bytes_and_outbox` | PUT 已落盘、201 被扣住 → kill | 远端字节精确、outbox 未 ack；重开重放 412+GET 验证后仅 ack 一次，绝不覆盖 |
| 2 | `kill_during_original_upload_before_remote_commit_leaves_no_partial_remote_object` | 原件上传 body 未读 → kill | 远端无对象、暂存原件 SHA 不变、仅剩私有临时文件且不被复用 |
| 3 | `replay_of_an_already_committed_immutable_revision_is_412_and_never_rewritten` | 远端已有同字节对象 | 412 → GET 验证 → ack；对象数与摘要不变 |
| 4 | `kill_during_verification_get_before_hash_keeps_remote_bytes_and_outbox` | 验证 GET 只发前缀 → kill | 无 hash 比较、无 ack；重放 412 且字节不变 |
| 5 | `truncated_verification_get_is_refused_without_acknowledgement` | 验证 GET 截断+RST | 传输失败（dav IO），无 ack、无远端变更；重试才 ack |
| 6 | `kill_while_acknowledging_after_verified_get_never_duplicates_or_loses_work` | 验证 GET 已返回、外部 `BEGIN IMMEDIATE` 挡住 ack → kill | outbox ∈ {0,1} 两分支都收敛到：1 个远端对象、1 条 history、outbox 空 |
| 7 | `abrupt_process_exit_after_outbox_commit_keeps_one_remote_object_and_no_pending_row` | ack 已完成、检出请求在途 → `_Exit(7)` | 退出码 7；远端 1 对象、outbox 空；重启不重复发布 |
| 8 | `kill_during_original_download_leaves_no_published_cache_identity` | 原件下载 body 中途 kill | 无 `<sha>.txt`、无 revision 落库；只剩私有临时；重试原子发布精确字节 |
| 9 | `original_download_timeout_removes_private_temp_and_keeps_pending_identity` | 原件下载 stall 超过 timeout | 有界超时（dav IO，http 0）、临时全清、无部分身份；重试成功 |
| 10 | `cached_original_identity_is_reverified_before_reuse` | 缓存原件被同长度篡改 | hash 状态拒绝、不偷偷覆盖、history 不变；修复后通过 |
| 11 | `remote_original_with_wrong_bytes_is_never_published_as_local_identity` | 远端原件字节与身份不符 | hash 拒绝、不发布缓存身份、不落 revision |
| 12 | `real_401_is_reported_without_acknowledgement_or_implicit_retry` | 真实 401 | dav AUTH + http 401、无 ack、等待期零请求；显式重试成功 |
| 13 | `real_403_is_reported_without_acknowledgement_or_implicit_retry` | 真实 403 | dav HTTP + http 403、无 ack、零隐式重放 |
| 14 | `real_429_retry_after_is_not_followed_by_implicit_replay` | 真实 429 + Retry-After | http 429、无 ack、Retry-After 窗口内零请求；显式重试 PUT 序列 `[429, 201]` |
| 15 | `real_503_during_publication_retains_outbox_and_republishes_on_explicit_retry` | 真实 503 | 远端未落盘、outbox 保留、零隐式重试；显式重试 `[503, 201]` |
| 16 | `mid_sweep_503_keeps_completed_shards_and_resumes_at_the_failed_shard` | 第 41 个 shard 的 PROPFIND 503 | `completed_shards=40`、`shard=40`；再次 start 从 40 续跑至 256 |
| 17 | `connection_reset_during_put_body_resolves_by_get_and_keeps_outbox` | PUT body 中途 RST | 视为歧义 IO → GET 判空（http 404）、无提交、outbox 保留 |
| 18 | `bounded_publication_timeout_leaves_no_remote_object_and_keeps_outbox` | PUT 无响应超过 timeout | 有界失败、远端无对象、outbox 保留；显式重试成功 |
| 19 | `existing_immutable_object_with_foreign_bytes_is_not_overwritten_or_acked` | 不可变路径上已有异字节 | 412 后 GET 判 hash 不符 → 拒绝 ack；异字节原样保留 |
| 20 | `same_account_reopen_after_forced_kill_resumes_without_rebinding` | kill 后同账号重开 | 绑定文件字节不变、无 ACCOUNT、outbox 一次清空 |
| 21 | `different_account_after_forced_kill_is_refused_before_any_request` | kill 后换账号 | 状态 4（ACCOUNT）、零新请求、绑定与 outbox 不变 |

## 5. 保留原 20 项

`tests/reader_session/check_session.py` **原样运行**（未改一行、未删一条断言、未放宽阈值），其 `result.json` 由本包认证：

- `accepted is True`、`source_sha == GITHUB_SHA`、`run_id/attempt` 与本包一致；
- 检查项集合逐字等于 `boundaries.ORIGINAL_SESSION_CHECKS`（20 条）；
- 汇总作业再校验一次，缺项或漂移即拒绝整轮。

本包的 21 条与这 20 条在同一 source/run/attempt 下分别成证，互不替代；报告不能冒充功能达标——`three_platform_accepted` 只由汇总作业给出，`host_ui_accepted`/`metadata_projection_accepted`/`complete_product` 恒为 `false`。

## 6. 明确未覆盖（不授予）

`boundaries.UNCOVERED_LIMITS` 逐平台记录，汇总作业拒绝任何“悄悄漏掉一条”的报告：

1. `atomic_rename_to_revision_receive_single_instruction_window`：原件 rename 到 revision receive 之间的单指令窗口无外部可观测边界，不声称覆盖。
2. `fixture_store_durability_before_response_flush`：夹具自身的落盘持久性属于夹具，不属于客户端契约。
3. `sqlite_page_torn_write_under_sigkill`：存储层页级撕裂归 store owner，本次只声明 outbox/history 的身份不变量。
4. `host_ui_projection_and_other_platform_hosts`：宿主投影、UI、Android/iOS 宿主与六目标 SDK 属其他 owner。
5. `third_party_server_retry_and_backoff_policy`：真实第三方 WebDAV 的重试/退避策略不复现，只用显式状态码。

第 6 条边界的 ack 窗口用**外部排他写锁**（`BEGIN IMMEDIATE`）作为可观测边界，不是共享代码里的注入点；实测记录了两分支中的实际那一支。

## 7. 云端执行

`.github/workflows/reader-sync-resilience.yml`：

- `boundaries` 作业矩阵 `ubuntu-22.04 / windows-2022 / macos-15`，每平台：门禁 → 构建安装 product/webdav/revisions/sync/session → 构建消费者 → 跑原 20 项 → 跑 21 条新边界 → 上传工件（排除 `*.key`）。
- 门禁：`HEAD == GITHUB_SHA`、起点为祖先、SDK 树与产品 SQL/共享模块逐字相等、`git diff --name-only <start> HEAD` 全在本包白名单。
- `aggregate` 作业：`needs: [boundaries]` + `actions/download-artifact`，`check_evidence.py` 校验三平台齐全、source/run/attempt 一致、21 条具名边界全 `pass` 且 `expected/actual` 非空、原 20 项漂移即失败、未覆盖清单一致、工件内无 `*.key`，并记录每份 `result.json` 的 SHA-256。

工件命名：`reader-sync-resilience-<runner.os>-<run_id>-<attempt>`、`reader-sync-resilience-aggregate-<run_id>-<attempt>`。

## 8. 本轮结果（实际证据）

### 8.1 受测源与运行

| 项 | 值 |
| --- | --- |
| 完整受测 source SHA | `79a4070059a0806ca91ce9b9092e5f71eca50e4e` |
| run / attempt | `40079870542` / `1` |
| workflow | `.github/workflows/reader-sync-resilience.yml` |
| 固定实现起点 | `f43baf9182d75907c0cb5d6f77048f27bca8c950`（祖先，门禁校验） |
| SDK 保护树 | `9854061be331fe603a1822d9b2b36ee357154927`（逐字相等） |
| 产品 schema / 共享模块 | 未改（`apps/reader/store`、`session`、`sync`、`revisions`、`extras/webdav`、`extras/opds` 逐字相等） |
| 三个平台请求总数 | 各 2827（三平台完全一致） |

### 8.2 作业

| job id | 名称 | 结论 | 起止（UTC） |
| --- | --- | --- | --- |
| 120830996325 | fault boundaries (ubuntu-22.04) | success | 08:54:43 → 08:58:36 |
| 120830996147 | fault boundaries (windows-2022) | success | 08:54:43 → 08:57:23 |
| 120830996357 | fault boundaries (macos-15) | success | 08:56:17 → 08:59:13 |
| 120831849724 | strict same-source three-platform aggregate | success | 08:59:15 → 08:59:28 |

### 8.3 工件身份（带 run/attempt，非空字节、有效期、SHA-256）

| 名称 | id | 字节 | SHA-256（上传日志一致） | 过期 |
| --- | --- | --- | --- | --- |
| `reader-sync-resilience-Linux-40079870542-1` | 12555105747 | 2969210 | `sha256:2ea2905b9490ba3191568d1d03bf211f4fa03346eae9601d038a109693e06660` | 2027-01-22 |
| `reader-sync-resilience-Windows-40079870542-1` | 12554886282 | 2741000 | `sha256:78ab2a2f7b8e394ee8fd01d30e2e195cafd024dac29681232af6e8bed04b755a` | 2027-01-22 |
| `reader-sync-resilience-macOS-40079870542-1` | 12554952204 | 2572269 | `sha256:efdc7790188648aa1e8f9f552adf6f559a82a32d618e5f2754c6022b510182c4` | 2027-01-22 |
| `reader-sync-resilience-aggregate-40079870542-1` | 12555310099 | 1976 | `sha256:86b0d99357e4b21d140dfcee858f463e582d96190a04a336885d452a8766a20d` | 2027-01-22 |

工件内不含私钥（`!build/**/certificates/*.key`，汇总作业再次断言无 `*.key`）。

### 8.4 平台摘要（严格汇总实算）

| 平台 | 21 条边界 | 原 20 项 | 请求数 | 用时(s) | `result.json` SHA-256 | 原 20 项报告 SHA-256 |
| --- | --- | --- | --- | --- | --- | --- |
| Linux | 21/21 | 20/20 | 2827 | 80.88 | `1d5a977f...c0cb` | `5d747b4a...9c83` |
| Windows | 21/21 | 20/20 | 2827 | 45.34 | `1aa393c3...26bf` | `2f0e6fd3...fd29` |
| macOS | 21/21 | 20/20 | 2827 | 64.76 | `be671c99...44ab` | `9bea01ca...d9d1` |

消费者身份：Linux `6da09ecc…`、Windows `ba43bac0…`、macOS `55a285b2…`；协议 owner 的 `revision-consumer` 同源构建。
平台报告均自报 `three_platform_accepted: false`，只有汇总作业给出 `three_platform_accepted: true`。

### 8.5 逐项实测

退出身份为真实进程：POSIX 为 `SIGKILL`（rc=-9），Windows 为 `TerminateProcess`（rc=1），第 7 条为自我 `_Exit(7)`。
完整 expected/actual 见 `docs/validation/reader-sync-resilience.json` 与各平台工件内 `resilience-evidence/result.json`。

#### 1. `put_committed_before_ack_response_withheld_then_kill_preserves_remote_bytes_and_outbox`

- 预期：A kill while the 201 is withheld leaves exactly the committed remote bytes and the unacknowledged outbox row; the next sweep replays conditionally (412), verifies by GET, acknowledges once and never rewrites the immutable object.
- Linux：exit=pid 8021, SIGKILL, rc=-9 · put_outcomes=[201,412] · outbox_after_kill=1 · outbox_after_resume=0 · public_read_heads=1 · readback_exact=true
- Windows：exit=pid 5768, TerminateProcess, rc=1 · put_outcomes=[201,412] · outbox_after_kill=1 · outbox_after_resume=0 · public_read_heads=1 · readback_exact=true
- macOS：exit=pid 11000, SIGKILL, rc=-9 · put_outcomes=[201,412] · outbox_after_kill=1 · outbox_after_resume=0 · public_read_heads=1 · readback_exact=true

#### 2. `kill_during_original_upload_before_remote_commit_leaves_no_partial_remote_object`

- 预期：A kill inside the upload body leaves no remote object and no rewritten staged original; the only residue is a private transfer temporary that the next sweep never reuses.
- Linux：exit=pid 8303, SIGKILL, rc=-9 · put_outcomes=["undelivered",201] · remote_object_absent=true · leftover_temporaries=[".reader-sync-3f237239aa424ec794e2ad88e8131715.tmp"] · staged_bytes=936000
- Windows：exit=pid 6748, TerminateProcess, rc=1 · put_outcomes=["undelivered",201] · remote_object_absent=true · leftover_temporaries=[".reader-sync-7d1a5bf016dc4ee7bea268df11a08305.tmp"] · staged_bytes=936000
- macOS：exit=pid 11007, SIGKILL, rc=-9 · put_outcomes=["undelivered",201] · remote_object_absent=true · leftover_temporaries=[".reader-sync-bf78b1e19f8648b48fb6eec620daaabb.tmp"] · staged_bytes=936000

#### 3. `replay_of_an_already_committed_immutable_revision_is_412_and_never_rewritten`

- 预期：Publishing a row that is already on the server is answered 412 and acknowledged only after a byte-identical GET; the remote object count and digest never change.
- Linux：put_outcomes=[412] · object_count_for_id=1 · outbox=0 · pushed=1
- Windows：put_outcomes=[412] · object_count_for_id=1 · outbox=0 · pushed=1
- macOS：put_outcomes=[412] · object_count_for_id=1 · outbox=0 · pushed=1

#### 4. `kill_during_verification_get_before_hash_keeps_remote_bytes_and_outbox`

- 预期：A kill inside the verification GET body cannot acknowledge; the retained row is replayed after restart and the immutable remote bytes are unchanged.
- Linux：exit=pid 8603, SIGKILL, rc=-9 · put_outcomes=[412,412] · outbox_after_kill=1 · outbox_after_resume=0
- Windows：exit=pid 4212, TerminateProcess, rc=1 · put_outcomes=[412,412] · outbox_after_kill=1 · outbox_after_resume=0
- macOS：exit=pid 11087, SIGKILL, rc=-9 · put_outcomes=[412,412] · outbox_after_kill=1 · outbox_after_resume=0

#### 5. `truncated_verification_get_is_refused_without_acknowledgement`

- 预期：A verification GET closed before its declared length is reported as a native transport failure with no acknowledgement and no remote mutation; the retry then acknowledges.
- Linux：failure_status=3 · failure_dav_code=3 · failure_http_status=0 · outbox_after_failure=1 · outbox_after_retry=0
- Windows：failure_status=3 · failure_dav_code=3 · failure_http_status=0 · outbox_after_failure=1 · outbox_after_retry=0
- macOS：failure_status=3 · failure_dav_code=3 · failure_http_status=0 · outbox_after_failure=1 · outbox_after_retry=0

#### 6. `kill_while_acknowledging_after_verified_get_never_duplicates_or_loses_work`

- 预期：A kill while the acknowledgement is blocked by an external exclusive database write lock either leaves the row pending or already acknowledged; both states converge on one remote object, one history row and an empty outbox after restart.
- Linux：exit=pid 9181, SIGKILL, rc=-9 · outbox_after_kill=1 · history_after_kill=1 · outbox_after_resume=0 · object_count_for_id=1
- Windows：exit=pid 4512, TerminateProcess, rc=1 · outbox_after_kill=1 · history_after_kill=1 · outbox_after_resume=0 · object_count_for_id=1
- macOS：exit=pid 11223, SIGKILL, rc=-9 · outbox_after_kill=1 · history_after_kill=1 · outbox_after_resume=0 · object_count_for_id=1

#### 7. `abrupt_process_exit_after_outbox_commit_keeps_one_remote_object_and_no_pending_row`

- 预期：An abrupt exit after the acknowledgement keeps the committed object and the empty outbox; the restart republishes nothing and keeps a single immutable history row.
- Linux：exit=pid 9463, self exit without unwinding, rc=7 · outbox_after_exit=0 · put_outcomes=[201] · object_count_for_id=1 · outbox_after_restart=0
- Windows：exit=pid 236, self exit without unwinding, rc=7 · outbox_after_exit=0 · put_outcomes=[201] · object_count_for_id=1 · outbox_after_restart=0
- macOS：exit=pid 11331, self exit without unwinding, rc=7 · outbox_after_exit=0 · put_outcomes=[201] · object_count_for_id=1 · outbox_after_restart=0

#### 8. `kill_during_original_download_leaves_no_published_cache_identity`

- 预期：A kill inside the original body leaves no cache identity (no <sha>.<format> file) and no received revision; only private transfer temporaries remain, and the retry publishes the exact bytes atomically.
- Linux：exit=pid 9735, SIGKILL, rc=-9 · history_after_kill=0 · leftover_temporaries=[".exr-webdav-f8c42ee107fe17607953e634ae14a83a.tmp",".reader-sync-ef994836c4444d57aa7e60bfe3f15c5d.tmp"] · originals_verified=1
- Windows：exit=pid 7644, TerminateProcess, rc=1 · history_after_kill=0 · leftover_temporaries=[".exr-webdav-7644-2.tmp",".reader-sync-e5991a4b81774786b2c06a07c28fbab4.tmp"] · originals_verified=1
- macOS：exit=pid 11336, SIGKILL, rc=-9 · history_after_kill=0 · leftover_temporaries=[".exr-webdav-8fb3595ced0f328451602d14f9fbc71a.tmp",".reader-sync-d6e014ac31704745be3473ac9ddaa224.tmp"] · originals_verified=1

#### 9. `original_download_timeout_removes_private_temp_and_keeps_pending_identity`

- 预期：A transfer timeout inside the original download is reported as a bounded native transport failure, leaves no temporary and no partial identity, and the explicit retry publishes the exact bytes.
- Linux：failure_status=3 · failure_dav_code=3 · elapsed_seconds=1.57 · timeout_ms=1500 · leftover_temporaries=[]
- Windows：failure_status=3 · failure_dav_code=3 · elapsed_seconds=4.02 · timeout_ms=1500 · leftover_temporaries=[]
- macOS：failure_status=3 · failure_dav_code=3 · elapsed_seconds=1.67 · timeout_ms=1500 · leftover_temporaries=[]

#### 10. `cached_original_identity_is_reverified_before_reuse`

- 预期：A same-length corrupted cache identity is refused with the hash status and is never overwritten behind the host, while the verified bytes keep the history unchanged.
- Linux：corrupt_status=5 · cache_unchanged_after_refusal=true · history=1
- Windows：corrupt_status=5 · cache_unchanged_after_refusal=true · history=1
- macOS：corrupt_status=5 · cache_unchanged_after_refusal=true · history=1

#### 11. `remote_original_with_wrong_bytes_is_never_published_as_local_identity`

- 预期：A remote original with the right length but the wrong digest is refused with the hash status, publishes no cache identity and receives no revision.
- Linux：failure_status=5 · cache_identity_absent=true · history=0
- Windows：failure_status=5 · cache_identity_absent=true · history=0
- macOS：failure_status=5 · cache_identity_absent=true · history=0

#### 12. `real_401_is_reported_without_acknowledgement_or_implicit_retry`

- 预期：A real 401 is reported as an authentication failure with the status preserved, no acknowledgement, no automatic replay, and the row is published only on an explicit retry.
- Linux：failure_status=3 · failure_dav_code=6 · failure_http_status=401 · rejected_requests=1 · implicit_requests_during_wait=0
- Windows：failure_status=3 · failure_dav_code=6 · failure_http_status=401 · rejected_requests=1 · implicit_requests_during_wait=0
- macOS：failure_status=3 · failure_dav_code=6 · failure_http_status=401 · rejected_requests=1 · implicit_requests_during_wait=0

#### 13. `real_403_is_reported_without_acknowledgement_or_implicit_retry`

- 预期：A real 403 stays a reported failure with the status preserved, no acknowledgement and no implicit replay; the retained row is published by an explicit retry.
- Linux：failure_status=3 · failure_dav_code=5 · failure_http_status=403 · rejected_requests=1 · outbox_after_failure=1
- Windows：failure_status=3 · failure_dav_code=5 · failure_http_status=403 · rejected_requests=1 · outbox_after_failure=1
- macOS：failure_status=3 · failure_dav_code=5 · failure_http_status=403 · rejected_requests=1 · outbox_after_failure=1

#### 14. `real_429_retry_after_is_not_followed_by_implicit_replay`

- 预期：A real 429 with Retry-After is surfaced with no acknowledgement and no request during the advertised interval; the explicit retry then publishes the immutable bytes once.
- Linux：failure_status=3 · failure_http_status=429 · put_outcomes=[429,201] · requests_during_retry_after=0 · outbox_after_retry=0
- Windows：failure_status=3 · failure_http_status=429 · put_outcomes=[429,201] · requests_during_retry_after=0 · outbox_after_retry=0
- macOS：failure_status=3 · failure_http_status=429 · put_outcomes=[429,201] · requests_during_retry_after=0 · outbox_after_retry=0

#### 15. `real_503_during_publication_retains_outbox_and_republishes_on_explicit_retry`

- 预期：A real 503 during publication is reported, commits nothing remotely, keeps the outbox row and is not retried implicitly; the explicit retry publishes the exact bytes once.
- Linux：failure_status=3 · failure_http_status=503 · put_outcomes=[503,201] · remote_absent_after_failure=true · requests_during_retry_after=0
- Windows：failure_status=3 · failure_http_status=503 · put_outcomes=[503,201] · remote_absent_after_failure=true · requests_during_retry_after=0
- macOS：failure_status=3 · failure_http_status=503 · put_outcomes=[503,201] · remote_absent_after_failure=true · requests_during_retry_after=0

#### 16. `mid_sweep_503_keeps_completed_shards_and_resumes_at_the_failed_shard`

- 预期：A real 503 in the middleware of the sweep keeps the 40 completed shards, reports the failed shard and resumes there on the next explicit start instead of restarting work.
- Linux：failure_status=5 · failure_http_status=503 · completed_shards_at_failure=40 · shard_at_failure=40 · completed_shards_after_restart=256 · sweeps_after_restart=1
- Windows：failure_status=5 · failure_http_status=503 · completed_shards_at_failure=40 · shard_at_failure=40 · completed_shards_after_restart=256 · sweeps_after_restart=1
- macOS：failure_status=5 · failure_http_status=503 · completed_shards_at_failure=40 · shard_at_failure=40 · completed_shards_after_restart=256 · sweeps_after_restart=1

#### 17. `connection_reset_during_put_body_resolves_by_get_and_keeps_outbox`

- 预期：A connection reset inside the PUT body is treated as an ambiguous transport outcome: nothing is committed, the verification GET reports the object absent and the outbox row stays until an explicit retry publishes it.
- Linux：failure_status=3 · failure_dav_code=5 · failure_http_status=404 · remote_absent_after_reset=true · outbox_after_failure=1 · retry_status=0
- Windows：failure_status=3 · failure_dav_code=5 · failure_http_status=404 · remote_absent_after_reset=true · outbox_after_failure=1 · retry_status=0
- macOS：failure_status=3 · failure_dav_code=5 · failure_http_status=404 · remote_absent_after_reset=true · outbox_after_failure=1 · retry_status=0

#### 18. `bounded_publication_timeout_leaves_no_remote_object_and_keeps_outbox`

- 判定范围：停滞请求返回失败且端到端耗时小于测试的 30 s 防挂起上限；不提交远端对象，outbox 保留，显式重试可发布精确字节。`timeout_ms=1200` 是传输配置，不能据此宣称整个操作在 1200 ms 内结束。
- Linux：failure_status=3 · elapsed_seconds=1.39 · timeout_ms=1200 · remote_absent_after_timeout=true · outbox_after_failure=1
- Windows：failure_status=3 · elapsed_seconds=4.02 · timeout_ms=1200 · remote_absent_after_timeout=true · outbox_after_failure=1
- macOS：failure_status=3 · elapsed_seconds=1.3 · timeout_ms=1200 · remote_absent_after_timeout=true · outbox_after_failure=1

#### 19. `existing_immutable_object_with_foreign_bytes_is_not_overwritten_or_acked`

- 预期：A different body already stored at the immutable path is preserved byte for byte, the acknowledgement is refused with the hash status, and only the correct bytes let the replay acknowledge.
- Linux：failure_status=5 · put_outcomes=[412] · foreign_bytes_preserved=true · outbox_after_retry=0
- Windows：failure_status=5 · put_outcomes=[412] · foreign_bytes_preserved=true · outbox_after_retry=0
- macOS：failure_status=5 · put_outcomes=[412] · foreign_bytes_preserved=true · outbox_after_retry=0

#### 20. `same_account_reopen_after_forced_kill_resumes_without_rebinding`

- 预期：After a forced kill the same account and root reopen with no rebinding, the binding bytes stay identical, the retained row is acknowledged once and the history is intact.
- Linux：exit=pid 10422, SIGKILL, rc=-9 · binding_unchanged=true · outbox_after_resume=0 · pushed_on_resume=1
- Windows：exit=pid 864, TerminateProcess, rc=1 · binding_unchanged=true · outbox_after_resume=0 · pushed_on_resume=1
- macOS：exit=pid 11742, SIGKILL, rc=-9 · binding_unchanged=true · outbox_after_resume=0 · pushed_on_resume=1

#### 21. `different_account_after_forced_kill_is_refused_before_any_request`

- 预期：A different account on the killed store is refused with the account status before any request, the binding is not rewritten and the retained outbox row is untouched.
- Linux：exit=pid 10962, SIGKILL, rc=-9 · refusal_status=4 · requests_after_refusal=0 · outbox_after_refusal=1
- Windows：exit=pid 2416, TerminateProcess, rc=1 · refusal_status=4 · requests_after_refusal=0 · outbox_after_refusal=1
- macOS：exit=pid 11775, SIGKILL, rc=-9 · refusal_status=4 · requests_after_refusal=0 · outbox_after_refusal=1

### 8.6 跨平台一致性

21 条边界的远端对象 SHA-256、PUT 结果序列与模块状态码在三平台**逐字一致**；仅终止身份与耗时不同。
这条一致性由汇总作业逐份报告复算，不是人工比对。

### 8.7 原失败（全部保留，未删断言）

| run | source | 结果 | 根因 | 处置 |
| --- | --- | --- | --- | --- |
| 40076301578 | 5d8c351c | 三平台均在第 2 条失败 | 共用夹具命名空间：一次 256-shard 扫描把别的边界的 revision 也拉进了 history | 每个设备独占 `/<boundary>/`，路径助手均取设备描述 |
| 40076966322 | 6a34f2d3 | 1–11 通过，第 12 条 seed 被拒 | `revision-consumer` 要求 32 位小写十六进制 entity key，`'g'*32` 非法 | 12–21 改用互异十六进制 key |
| 40077850433 | ab810bfc | Linux/macOS 通过，Windows 第 20 条失败 | 活着的 worker 以零共享方式占用 `<product>.sync-account`，回读抛 `PermissionError` | 绑定文件只在属主进程退出后回读 |
| 40078460400 | 625bcd36 | 三平台通过，汇总未找到报告 | `upload-artifact` 以 `build/` 为根打包多路径工件，汇总假定的层级不对 | 以工件目录名（内含 run/attempt）绑定报告 |
| 40078978609 | 984a5b7a | 全绿（被日志输出提交取代） | — | — |
| 40079404890 | 464466fd | 全绿（被逐项记录输出提交取代） | — | — |

### 8.8 交付与未完成

- 交付：`tests/reader_sync_resilience/**`（21 条边界、阶段握手夹具、独立 `resilience-consumer`、逐平台验收、严格汇总）、`.github/workflows/reader-sync-resilience.yml`、本文件、`docs/validation/reader-sync-resilience.json`。
- 未授予：宿主 UI、元数据投影、六目标 SDK、Android/iOS 宿主、真实第三方服务与真实账号（见第 6 节与 `granted` 字段）。
- 未完成/待 root：统一审查与普通合并、与其他 15 路的共同源码复验；本包未发现需修改共享实现的缺陷，因此没有提交共享补丁。

## 9. 限制

- 夹具是 IPv4 回环 + 受信证书，不涉及真实第三方服务与真实账号；跨平台只覆盖三个原生宿主，不等于六目标 SDK。
- 21 条边界证明的是**这些具体故障点上的一致性**，不外推到未列出的边界（见第 6 节）。
- `timeout_ms` 配置与端到端耗时分别记录。Windows 用 `WinHttpSetTimeouts` 为各阶段设置超时，调用返回后的截止时间检查不能中断正在阻塞的系统调用；本轮 1200/1500 ms 配置下均观测到 4.02 s，Linux/macOS 分别为 1.39/1.57 s 与 1.30/1.67 s。这些值证明本轮故障会返回，并满足下载 <45 s、发布 <30 s 的既有防挂起断言；没有证明配置值是整个操作的严格上界，也没有授予产品延迟预算。原观测、断言和工件保持不变。

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
| `stall_before_headers` | 不回头、不回体 | timeout 上界 |
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

## 8. 本轮结果

（本轮 run 完成后按实际工件回填：source SHA、run/attempt/job、逐平台逐项结果、工件 id/字节/digest/有效期、原失败与剩余工作。）

## 9. 限制

- 夹具是 IPv4 回环 + 受信证书，不涉及真实第三方服务与真实账号；跨平台只覆盖三个原生宿主，不等于六目标 SDK。
- 21 条边界证明的是**这些具体故障点上的一致性**，不外推到未列出的边界（见第 6 节）。

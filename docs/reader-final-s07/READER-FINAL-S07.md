# S07 raw 同步多 peer 故障与幂等回归

状态：**实现已提交，云端尚未执行**；`accepted=false`，`adopted=false`。本文件在真实运行后追加证据小节。

固定实现起点：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`。分支 `codex/reader-fw-s07`。

## 1. 范围与不变项

新增（且仅新增）：

- `tests/reader_final_s07/`：只读来源守卫、三 peer 临时 HTTPS 夹具与验收、驱动、严格汇总。
- `.github/workflows/reader-final-s07.yml`：只由本分支 / 本包路径触发，矩阵 `max-parallel: 2`。
- `docs/reader-final-s07/`：本契约与 `validation.json`。
- `HANDOFF-RESULT.md`：本分支交回状态。

不修改（守卫逐字校验）：`apps/reader/**`、`extras/**`、SDK 保护树 `src/ include/ cmake/ CMakeLists.txt`、`examples/**`、`tests/fixtures/**`、全部原 tests 目录（含冻结 raw7 模块、G07、原消费者）、`bindings/`、`tools/`。守卫要求 `git diff --name-only 0889f7d1 HEAD` 的每一项都落在上面四个新增路径内，且 `git diff --exit-code 0889f7d1 HEAD -- <冻结树>` 成功。

## 2. 复用的冻结资产（未改一字节）

| 资产 | 用途 | 身份 |
| --- | --- | --- |
| `tests/reader_selector_bytes/run.py` | 真实公开 SDK 捕获（11 条真实 wire、真实 8845 字节 PDF） | `source_guard.frozen_identities.core_run_py_sha256` |
| `tests/reader_raw_store_companions/CMakeLists.txt` + `*.cpp/*.c` | 安装后的 raw7 消费者 `raw-bootstrap/raw-sync/raw-revision/raw-commands/raw-session/raw-guard` | `raw7_consumers_cmake_sha256` 等 |
| `tests/reader_raw_store_companions/tls.py` | 冻结的双 peer 真 TLS 验收（9 项），同一次运行的前置证据 | `raw7_tls_py_sha256` |
| `tests/reader_session/check_session.py` | 原 20 项账号会话验收 | 由 G07 汇总裁定 |
| `tests/reader_sync_resilience/*` | G07 21 条故障边界（原样运行，含 `boundaries.py` 具名清单） | `g07_checker_sha256` |
| `tests/reader_revisions|sync|commands|session/consumer` | 全部协议消费者（raw 与 0.1.0/0.3.0 legacy 两份） | 各自 sha256 |

## 3. 唯一的内存替换（可审计）

冻结捕获 core 的 8 行归属声明把 `examples/` 与 `apps/reader/store` 钉在其自身起点 `b93b4a2f`；主线在 `b93b4a2f..0889f7d1` 之间改过 `examples/`（Apple/Linux 宿主 UI），因此该块在固定起点必然拒绝，不是本分支的改动。`run.py` 仅替换该块：

- 保留原样：`git diff --exit-code edddc463… HEAD -- src include cmake CMakeLists.txt`；
- 替换为：`git diff --exit-code 0889f7d1 HEAD -- src include cmake CMakeLists.txt apps/reader/store examples tests/fixtures extras/opds extras/webdav` + 本包守卫；
- 原块文本、块 sha256、替换文本、补丁后全文 sha256 全部写进 `result.json`。捕获、构建、协议/图用例、legacy 字节比对逐字未动。

没有其它源码替换，没有 SQL 造 wire：所有合法成功 wire 只由冻结模块（`reader_revision_local*`、typed command、`reader_revision_receive*`）产生；夹具只写两种**拒绝输入**并在证据里带字节与 sha256（第 6 项）。

## 4. 三 peer 拓扑与故障门

一个 IPv4 回环 + 已信任证书（`DNS:localhost,IP:127.0.0.1`）的 WebDAV 源，五个命名空间共存于同一 server root：

```
dav        sender / receiver-one / receiver-two（raw3）
legacy1    legacy-one（MAX2 v1 发送）→ legacy-receiver（MAX2 v1 接收）
legacy2    legacy-two（MAX2 v2 发送）
raw3       只放一条真实 v3 wire（给 MAX2 消费者拒绝用）
unknown    只放一条真实 v3 wire 把 anchor_version 改成 4（给 raw 消费者拒绝用）
```

服务端故障门（每次 `(method, path)` 消费一次，全部记录）：

| 门 | 语义 | 用途 |
| --- | --- | --- |
| `reset_before_commit` | 不读 body、不落盘、直接断连 | 断网重试 |
| `commit_then_drop` | body 已落盘，扣住响应断连 | 响应丢失 |
| `drop` | GET 不返回任何响应就断连 | 使验证 GET 失败 |

每个 peer 动作都是独立的原生进程（`raw-bootstrap/raw-sync/raw-revision/raw-commands` 或 legacy 消费者），因此"跨进程重开"是默认事实，不是声明。

## 5. 八条具名验收（顺序固定）

| # | id | 不变量 |
| --- | --- | --- |
| 1 | `real_capture_graph_and_original_identity_bootstrap` | 只引导真实捕获；导出 11 条 wire；原件 8845 字节 / `5627a430…` |
| 2 | `network_reset_before_commit_then_explicit_retry_publishes_exactly_once` | 远端无对象、outbox 全留；显式重试每条只发布一次并 ack |
| 3 | `response_lost_newer_head_then_old_request_retry_keeps_head_and_outbox` | 提交后响应与验证 GET 都丢失 → 收到更新 head → 重试旧请求：412+GET+一次 ack，head / history / outbox 不变 |
| 4 | `out_of_order_parent_graph_child_before_parent_then_complete` | 先收子件：字节精确、`missing_parents=1`、`projection_safe=0`、子件 `complete=0`；父件到达后单一完整 head |
| 5 | `duplicate_wire_receive_is_idempotent_for_both_receivers` | 重复投递：无新 head、无新 history、无 outbox、无新远端对象、无 PUT |
| 6 | `unknown_anchor_version_refused_over_network_and_direct_receive` | 未知 anchor 版本经真实网络与直接 receive 都被 `FORMAT` 拒绝且不写入；MAX2 同时拒绝 v3 与 v4 |
| 7 | `legacy_max2_consumers_coexist_without_corruption` | 两个 MAX2 发送者与一个 MAX2 接收者在同一 root 上传送 legacy1/legacy2，字节精确，raw3 拒绝后自身历史与 outbox 不变 |
| 8 | `exact_wire_ids_parents_and_original_hash_after_cross_process_reopen` | 15 条 wire 在三 peer 上 ID / 字节 / parents 逐项相等，原件 hash 相等，新进程重开 outbox 为空 |

第 4 项如何做到"子先于父"而不造数据：模块把 revision ID 当宿主提供的稳定 ID（`reader_command_context.revision_id`）。先用真实 typed book 命令建父件 `0500`（父 `0600`），再建子件 `0400`（父 `0500`），两条都由模块编码；客户端在同 shard 内按 `<id>-<sha>.json` 升序拉取，因此子件 `0400` 必然先被投递。游标用服务器上小于子件叶子的最大叶子，`limit=1` 精确只投一条。

## 6. 严格汇总（独立作业 / 独立 checkout）

`strict.py` 用 `gh api` 认证本次 run/attempt 的原工件：作业结论、artifact id、字节数、`sha256:` 摘要、有效期、`workflow_run.head_sha`；再只从工件字节复算：

1. 只读守卫仍是固定起点、冻结树零差异、改动路径都在本包白名单；
2. 工件内四份 precondition 报告的 sha256 与 `result.json` 记录一致，且 source/run/attempt 同源；G07 20 项与 21 条具名边界逐项吻合 `boundaries.py`；
3. 八条具名项齐全有序、`expected/actual` 非空；
4. 两平台的 15 条 wire 表（ID、字节 sha256、parents）、父图与远端对象清单逐项相等。

平台报告自报 `adopted/actual_hosts/complete_product = false`；汇总作业也不授予这些。

## 7. 授予与缺口

授予（本轮成功时）：三 peer raw 同步故障与幂等回归、冻结 raw7 模块未改、同次运行的冻结双 peer TLS 与 G07 前置。

不授予：真机宿主 UI、六目标 SDK 互通、真实第三方 WebDAV/真实账号、并发多写者、掉电级页撕裂、服务端重试/退避策略。逐条写进 `validation.json` 的 `gaps`，汇总作业拒绝丢失清单的报告。

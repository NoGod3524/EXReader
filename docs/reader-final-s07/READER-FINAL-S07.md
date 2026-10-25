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
| `discard_upload` | 读完整个 body、不落盘、扣住响应断连 | 断网重试（未提交） |
| `commit_then_drop` | body 已落盘，扣住响应断连 | 响应丢失 |
| `drop` | GET 不返回任何响应就断连 | 使验证 GET 失败 |

第 1 门**故意先读完 body 再断连**：若在客户端仍在上传时断连，Linux 上的原生客户端会被 SIGPIPE 直接杀死（见第 8 节观察），那只反映宿主边界，不反映同步契约。

每个 peer 动作都是独立的原生进程（`raw-bootstrap/raw-sync/raw-revision/raw-commands` 或 legacy 消费者），因此"跨进程重开"是默认事实，不是声明。

## 5. 八条具名验收（顺序固定）

| # | id | 不变量 |
| --- | --- | --- |
| 1 | `real_capture_graph_and_original_identity_bootstrap` | 只引导真实捕获；导出 11 条 wire；原件 8845 字节 / `5627a430…` |
| 2 | `network_drop_before_commit_then_explicit_retry_publishes_once` | 远端无对象、outbox 全留；显式重试每条只发布一次并 ack |
| 3 | `response_lost_newer_head_then_old_request_retry_keeps_head_and_outbox` | 提交后响应与验证 GET 都丢失 → 远端已有更新 head → 重试旧请求：412+GET+一次 ack，随后同一 step 收到更新 head，head / history / outbox 不变 |
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

## 7. 第 3 项的可达形式（契约事实，不是放宽断言）

冻结公开 step 的顺序是**先重放 pending 行、再拉取**（`reader_sync::step::push` 后 `pull`），而唯一不中断 step 的跳过条件是"本地原件缺失 **且** 远端原件 404"。因此"用一步只收更新 head、再用下一步重试旧请求"在冻结 API 下不可达。本包采用**更强且可达**的形式：

1. 旧请求的 PUT 已提交、响应与验证 GET 都丢失 → 行仍 pending（断言 remote 字节、outbox、head）；
2. 第二个 peer 经真实网络收到旧请求，并在其上发布更新 head；
3. 发送方一次 step：旧请求 PUT→**412**、GET→**200**（字节相等）、**仅一次** ack；随后同一 step 拉到更新 head。

请求轨迹（`retry_request_order`）逐条记录为 `[["put-old",412],["get-old",200],…,["get-newer",200]]`，因此"重试目标在服务器上已存在更 head、且更新 head 在重试之后才被交付"是被实测证明的。断言与第 2 节表格完全一致：单一 head = 更新 head、history=3（无重复行）、outbox 空、两条远端对象各 1 份、旧 wire 字节不变。

## 8. 观察（交给 root，本包不改 owner）：上传中断连会以 SIGPIPE 结束宿主

第 1 轮 Actions（source `3ccfe9f5`，run 40214771240 attempt 1）在 Linux 上暴露：当夹具在客户端仍在写 upload body 时直接断开（`shutdown(SHUT_RDWR)`+close），安装后的 `raw-sync` 进程被 **SIGPIPE 杀死**（`returncode=-13`，无任何 status 输出），而不是返回 `READER_SYNC_DAV`；同一 source 的 Windows 作业（WinHTTP）返回 `status=3 / dav_code=5 / http_status=404`。G07 第 17 条（"connection reset during put body"）没有覆盖这一点，因为它的 RST 发生在服务端已缓冲 body 之后。

含义：宿主进程若不忽略 SIGPIPE，可能被对端在上传途中的 RST 直接终止。这属于原生传输/宿主边界，本包**不修改** owner 代码，只交可复现步骤与两份原日志；建议由传输 owner 评估 `MSG_NOSIGNAL`/忽略 SIGPIPE，或由六平台宿主统一忽略。S07 的验收夹具已改为"读完 body 再断连"，不再依赖该行为。

## 9. 本轮结果（实际证据）

### 9.1 源与运行

| 项 | 值 |
| --- | --- |
| 完整受测 source SHA | `a436bfbeb522e129c790bd93d614c5fb84427048` |
| docs-only 封存 | 只含 `docs/reader-final-s07/` 与本包交回文件的后续提交（见分支 HEAD 与 `HANDOFF-RESULT.md`） |
| run / attempt | `40218562325` / `1` |
| workflow | `.github/workflows/reader-final-s07.yml`（矩阵 `max-parallel: 2`，同时仅一个 live run） |
| 固定实现起点 | `0889f7d1`（祖先；守卫实测 `frozen_tree_diff=0`） |
| 冻结 producer 清单 | 35 行，`sha256=6b00393cef1d7177c930732445def40239655c51b34b6a6bf46e31d42ca5faa7` |
| SDK | 批准 3.41 `edddc463…`；3.40 `9854061b…` 仅作祖先证明，本轮不构建 |

### 9.2 作业

| job id | 名称 | 结论 | 起止（UTC） |
| --- | --- | --- | --- |
| 121244918949 | three-peer regression (ubuntu-22.04) | success | 17:52:33 → 18:00:02 |
| 121244919145 | three-peer regression (windows-2022) | success | 17:52:33 → 17:59:03 |
| 121246669515 | strict same-attempt aggregate | success | 18:00:04 → 18:00:20 |

### 9.3 工件（`gh api` 认证的字节 / 摘要 / 有效期）

| 名称 | id | 字节 | SHA-256 | 过期 |
| --- | --- | --- | --- | --- |
| `reader-final-s07-Linux-40218562325-1` | 12608383795 | 147636 | `d5fbb5aba1139f345adb24ac2df6cad76f85b7c43e3dc22fb839203711143012` | 2027-01-23 |
| `reader-final-s07-Windows-40218562325-1` | 12608354542 | 147926 | `a70f1c37eb66764b7509d94d40680df749b7f109dafd19d36afeb51c88840c6a` | 2027-01-23 |
| `reader-final-s07-summary-40218562325-1` | 12609355634 | 1192 | `3345748d970d03305b31cfa37ca697324560af65f785b40742b3c9efcdfa7372` | 2027-01-23 |

工件内不含私钥（`!build/reader-final-s07/**/*.key`），两平台各 348 条受认证请求（全部带凭据、零未认证）。

### 9.4 同次运行的冻结前置（不拼接其它 run）

| 前置 | 结果 | result.json SHA-256 |
| --- | --- | --- |
| 冻结捕获 core | accepted，协议 30 项 + 图 11 项 | `5593972db58532770f13aec3a002d0e351f9194cb20725278c309fb5848e564b` |
| 冻结 raw7 双 peer 真 TLS | accepted，9/9，11 条精确 wire | `bd65667337a27be4afff6ea654bf9a740bb9f2bde1e9ac2d41cbf510a3dc6dc7` |
| G07 原 20 项账号会话 | accepted，20/20 | `966ab18ebd11b9951c6f6798b3e001eaa8ffb979ba9ce56d094fc880695694b4` |
| G07 21 条故障边界 | accepted，21/21（未覆盖 5 条原样记录） | `ac605a3801c1b291666e20d52e036c31825834f3190fc446f29e11859bcb851d` |

### 9.5 八条实测（两平台一致）

| # | id | 实测 |
| --- | --- | --- |
| 1 | bootstrap | 捕获 9 条 + 类型化 2 条 = 11 条；PDF 8845 B / `5627a430…`；book identity 8845 |
| 2 | 断网重试 | 失败 `status=3 dav=5 http=404`；被丢弃的上传 8845 B（同一 `5627a430…`）；远端无对象；outbox 11 条全留；重试 `pushed=11`、outbox 0、远端 revision 对象 11 |
| 3 | 响应丢失→更新 head→重试 | 丢失时 `status=3 dav=3 http=0`；远端已提交（`true`）、outbox 1；head@loss=`…0300`、history=2；重试后 head=`…0600`、history=3、outbox 0、旧 RID 不是 head、两条对象各 1 份、旧 wire 字节不变；请求序 `put-old 412 → get-old 200 → get-old 200 → get-newer 200` |
| 4 | 乱序父图 | 子件 `…0400` 先投递（`pulled=1`）：字节精确、`missing_parents=1`、`heads=2`、`projection_safe=0`、子 head `complete=0`；父件 `…0500` 到达后 `heads=1`（子件）、`complete=1`、`missing_parents=0`、history=5 |
| 5 | 重复 wire | 重复 `pulled=1`、created 0、history 5→5、head 集不变、outbox 0、窗口内 0 个 PUT、远端该对象 1 份；整 shard 重扫 `pulled=15` 仍不变 |
| 6 | 未知 anchor | 真实 wire 569 B（`anchor_version:3→4`）经真实网络与直接 receive 均 `status=4 / revision_code=4`；MAX2 对 v3 与 v4 均 4；两侧历史与 outbox 不变 |
| 7 | MAX2 共存 | legacy1/legacy2 各 `pushed=2`；MAX2 接收方 `pulled=2`、`pending_metadata=0`、`originals_verified=2`、wire 与原文字节精确、单一完整 head；同一 root 上 raw3 命名空间 15 个对象并存 |
| 8 | 精确字节/ID/parents/原件 hash + 跨进程重开 | 15 条 wire 在三 peer 上 `(id, sha256, bytes, parents)` 逐项相等；链 `…0001→…0300→…0600→…0500→…0400`；三 peer 新进程 `bootstrap check` 全过、outbox 0、无传输临时文件、缓存原件 `5627a430…` |

15 条 wire 的 SHA-256（两平台逐字一致，汇总作业复算）：

```
000…0001 937cd0f566d49a9729322ed74c0528a56d3b01de21ed0113e9a96f2877a46156  392B  []
000…0064 79d32397c80ef2e9e3a080f513e75c02e9e8bd87e09239a2b72151ec065ffc71  569B  []
000…0065 a1a5bc79052f9b1234a31872f1ec9f4f6323da6c308601c6e9b5929be494a575  603B  [0064]
000…0066 eb21b5c6eb7ec452db96a44bd9095eb0f0d20c89fd24c1e81872560d5e63c3bc  670B  []
000…0067 ab253edf9140df6be8cac8f24d7dd26979d4b6ccccc870fd4307dbe11d52723d  710B  [0066]
000…0068 389511142c03c171338f29bffa3ffaff326202d9f4e1905a828dc83fe81aa77a  671B  []
000…0069 d55c3630a6f98ebeaeab6bc904a677c8ac472bb234c7ba6e1b7e6fa47b01b498  706B  [0068]
000…006a 90460825fee47c80a64639c2cae89e025b8cdf1abb750777bb0177f05ff06a42  309B  [0069]
000…006b 582d7ce1096f65fab04bf55d7628b6805d309636e3e0cc5e97a64fbc8e74e3aa  712B  [006a]
000…0300 e65a34502f89b39b45ebba175389535c686200d9efbca10ca805189d64fcf3f1  431B  [0001]
000…0400 932f63bb1857fdad93d99cc86908e4cef962e23e97b61b8dc63219bf785c6874  433B  [0500]
000…0500 a1d0607b4ddfc2f2999dfcee9777904635d010747b3e70f7d26118b6d6f76df6  434B  [0600]
000…0600 8ae9428128890b109c269b9c49bf6774da176436598d650eb02c24611682a83c  430B  [0300]
000…1000 242e52dedacd5a3bf6b4d4a37a0b2dbd9c965d876fff7ca2b41851f5830307e9  210B  []
000…1001 d09c66dc800f20ea097f7e98cbec4ce43445300b576098d2621689da250414a5  436B  []
```

汇总作业实算：两平台 wire 表、父图、远端对象清单逐项相等（`true/true/true`）。平台报告自报 `adopted/actual_hosts/complete_product = false`，汇总也不授予这些。

### 9.6 原失败（保留，未删断言）

见 `validation.json` 的 `failures` 与第 8 节：第 1 轮 `3ccfe9f5` / run 40214771240 attempt 1 三作业失败，根因都在**本包自己的夹具**（Linux 写 body 期间断连 → 客户端 SIGPIPE；Windows 对"先收 head 再重试"的不可达顺序假设），冻结前置与第 1 项当时已通过。修复只动 `tests/reader_final_s07/` 与文档。

### 9.7 未验证（逐条 pending）

见 `gaps`：真实第三方 WebDAV/真实账号、六目标 SDK 互通与宿主 UI、同 store 并发多写、掉电级页撕裂、服务端重试/退避策略、四平台宿主投影。均**未测**，不授予。

## 10. 授予与缺口

授予（本轮成功时）：三 peer raw 同步故障与幂等回归、冻结 raw7 模块未改、同次运行的冻结双 peer TLS 与 G07 前置。

不授予：真机宿主 UI、六目标 SDK 互通、真实第三方 WebDAV/真实账号、并发多写者、掉电级页撕裂、服务端重试/退避策略。逐条写进 `validation.json` 的 `gaps`，汇总作业拒绝丢失清单的报告。

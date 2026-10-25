# S07 交回状态 — raw 同步多 peer 故障与幂等回归

结论：**两平台（Linux + Windows）实跑通过**；同 source/run/attempt 的严格汇总通过。`accepted=true`，`adopted=false`，不授予宿主 UI / 六平台互通 / 真实第三方服务。

## 1. 源与提交

| 项 | 值 |
| --- | --- |
| 固定实现起点 | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| **完整受测 source SHA** | `a436bfbeb522e129c790bd93d614c5fb84427048` |
| **docs-only 封存 SHA** | 本文件与 `docs/reader-final-s07/` 所在提交（`codex/reader-fw-s07` 的 HEAD；该提交不含 tests/ 或 workflow 改动，故不触发 CI） |
| 远端分支 | `origin/codex/reader-fw-s07` |
| 实现提交 | `3ccfe9f5`（首版）→ `a436bfbe`（修复本包夹具，受测） |
| workflow | `.github/workflows/reader-final-s07.yml`（只由本分支 + 本包路径触发；矩阵 `max-parallel: 2`；同时仅一个 live run） |

## 2. 运行与作业

| 项 | 值 |
| --- | --- |
| run / attempt | `40218562325` / `1` |
| job 121244918949 | three-peer regression (ubuntu-22.04) — success 17:52:33→18:00:02 UTC |
| job 121244919145 | three-peer regression (windows-2022) — success 17:52:33→17:59:03 UTC |
| job 121246669515 | strict same-attempt aggregate — success 18:00:04→18:00:20 UTC |

## 3. 工件（`gh api` 认证：字节数 / `sha256:` 摘要 / 有效期）

| 名称 | id | 字节 | SHA-256 | 过期 |
| --- | --- | --- | --- | --- |
| `reader-final-s07-Linux-40218562325-1` | 12608383795 | 147636 | `d5fbb5aba1139f345adb24ac2df6cad76f85b7c43e3dc22fb839203711143012` | 2027-01-23T17:52:31Z |
| `reader-final-s07-Windows-40218562325-1` | 12608354542 | 147926 | `a70f1c37eb66764b7509d94d40680df749b7f109dafd19d36afeb51c88840c6a` | 2027-01-23T17:52:31Z |
| `reader-final-s07-summary-40218562325-1` | 12609355634 | 1192 | `3345748d970d03305b31cfa37ca697324560af65f785b40742b3c9efcdfa7372` | 2027-01-23T17:52:31Z |

工件内不含私钥；两平台各 348 条受认证请求，全部带凭据、零未认证。每份工件自带 `result.json` + `preconditions/`（四份前置报告的原始字节，汇总作业按 SHA-256 复算）。

## 4. 实际执行的检查（8 条具名项，两平台一致）

1. `real_capture_graph_and_original_identity_bootstrap` — 捕获 9 + 类型化 2 = 11 条真实 wire；PDF 8845 B / `5627a430…`。
2. `network_drop_before_commit_then_explicit_retry_publishes_once` — 失败 `3/5/404`、被丢弃上传 8845 B、远端无对象、outbox 11 条全留；重试 `pushed=11`、outbox 0、远端 11 个 revision 对象。
3. `response_lost_newer_head_then_old_request_retry_keeps_head_and_outbox` — 丢失 `3/3/0`、远端已提交、outbox 1；重试序 `put-old 412 → get-old 200 → get-old 200 → get-newer 200`；head 从 `…0300` 变 `…0600`、history 2→3、outbox 0、旧 RID 非 head、旧 wire 字节不变、两对象各 1 份。
4. `out_of_order_parent_graph_child_before_parent_then_complete` — 子 `…0400` 先到：`missing_parents=1`、`heads=2`、`projection_safe=0`、`complete=0`；父 `…0500` 到达后 `heads=1`（子）、`complete=1`、history 5。
5. `duplicate_wire_receive_is_idempotent_for_both_receivers` — created 0、history 5→5、head 集不变、outbox 0、窗口 0 PUT、远端 1 份；整 shard 重扫 `pulled=15` 仍不变。
6. `unknown_anchor_version_refused_over_network_and_direct_receive` — 真实 v3 wire 单字段改 `anchor_version 3→4`（569 B）：raw 网络 `4/4`、直接 receive `4`；MAX2 对 v3、v4 均 `4`；两侧历史与 outbox 不变。
7. `legacy_max2_consumers_coexist_without_corruption` — legacy1/legacy2 各 `pushed=2`；MAX2 接收 `pulled=2`、`pending_metadata=0`、`originals_verified=2`、wire 与原文字节精确、单一完整 head；raw3 命名空间 15 对象并存。
8. `exact_wire_ids_parents_and_original_hash_after_cross_process_reopen` — 15 条 wire 的 `(id, sha256, bytes, parents)` 在三 peer 逐项相等，链 `0001→0300→0600→0500→0400`；三 peer 新进程 `bootstrap check` 全过、outbox 0、无传输临时文件、缓存原件 `5627a430…`。

同一次运行内的冻结前置（不是拼接其它 run）：冻结捕获 core accepted（协议 30 + 图 11）；冻结 raw7 双 peer TLS 9/9、11 条精确 wire；G07 原 20 项 20/20；G07 21 条边界 21/21。四份 `result.json` SHA-256：`5593972d…e564b`、`bd656673…c6dc7`、`966ab18e…694b4`、`ac605a38…b851d`。

## 5. 只读与复用（未改一字节）

守卫实测 `git diff --name-only 0889f7d1 HEAD` 只含本包四个路径，`git diff --exit-code 0889f7d1 HEAD -- <全部冻结树>` 为 0；冻结 producer 清单 35 行 `sha256=6b00393c…faa7`。冻结 raw7 模块、捕获 core、G07、原消费者全部按 0889 字节复用。

唯一的内存替换：冻结捕获 core 的归属声明块（原样记录 `sha256=4b352ffa…f3ca`，替换后全文 `sha256=1c4ab668…c5c1`），原因仅是该块把 `examples/` 钉在其自身起点 `b93b4a2f`，而主线在该起点之后改过 `examples/`。

## 6. 交 root 的 owner 观察（本包不改 owner 代码）

第 1 轮（source `3ccfe9f5`，run 40214771240 attempt 1）实测：夹具在客户端仍在上传 body 时断连，Linux 上安装后的 `raw-sync` 进程被 **SIGPIPE 杀死**（`returncode=-13`，无 status 输出），而不是返回 `READER_SYNC_DAV`；同 source 的 Windows（WinHTTP）返回 `3/5/404`。G07 第 17 条未覆盖此窗口（它的 RST 在服务端已缓冲 body 之后）。含义：不忽略 SIGPIPE 的宿主可被上传途中的 RST 直接终止；建议由传输 owner 评估 `MSG_NOSIGNAL`/宿主统一忽略。原日志：job 121233408152（Linux）与 121233408366（Windows）。S07 夹具已改为"读完 body 再断连"，不依赖该行为。

## 7. 原失败与未验证

原失败（保留，未删断言）：见 `docs/reader-final-s07/validation.json` 的 `failures`。第 1 轮三作业失败，两条根因都在**本包自己的夹具**（Linux 写 body 期间断连导致 SIGPIPE；Windows 对"先收 head 再重试"的不可达顺序假设），已在第 2 轮修复，冻结前置与第 1 项当时已通过。

第 3 项的顺序已按**契约事实**记录（第 7 节）：冻结 step 先重放 pending 再拉取，唯一不中断的跳过需要"本地原件缺失且远端 404"，因此"分两步先收 head 再重试"不可达；本包用更强且可达的形式（重试目标已存在更新 head、更新 head 在同一 step 之后交付）并由请求轨迹证明。

未验证（`pending`，不授予）：真实第三方 WebDAV 与真实账号、六目标 SDK 互通与宿主 UI、同 store 并发多写、掉电级页撕裂、服务端重试/退避策略、四平台宿主投影。

## 8. 复现

```
gh run view 40218562325 --log            # 两平台 + 汇总
gh run download 40218562325 -n reader-final-s07-Linux-40218562325-1 -D out
python -c "import json;print(json.load(open('out/result.json'))['three_peers']['checks'])"
```

最终产品授予由 root 控制。

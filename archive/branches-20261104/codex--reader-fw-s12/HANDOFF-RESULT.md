# S12 交回结果：Unicode 路径与书库状态跨配置回归

**状态：未验收（accepted=false）。** 三轮 CI 全部失败，失败原因全部在本包新增的测试工具里，
不在 owner 代码；第三轮之后已按证据修正，但**修正后的源码尚未在 Actions 执行**，因此不授予任何通过。
本包没有修改 `apps/`、SDK、原 `tests/`、原 workflow、预算或任何现有文件。

## 1. source / 分支

| 项 | 值 |
| --- | --- |
| 实现起点 | `0889f7d1e9a537c6c1b05456547e016b26e1cd85` |
| 批准 SDK 保护树（工作流逐字节比对） | `edddc463c06ed5731195cdb8f06b2df6dff7699e`（3.40 冻结树 `9854061b…` 在该起点已被 3.41 替换，事实如此记录） |
| 远端分支 | `codex/reader-fw-s12`（只此分支，无 PR、无默认分支、无 tag、无 Release） |
| 受测源码（三轮，全部失败） | `9babde99…`(run 40215053846) / `911db25d…`(40215267638) / `66379633…`(40218361806) |
| 修正后源码（未上云） | `afceae3a3a7a009ab396a273f729e115acf397fc` |
| 文档封存 | `417bb76ad68e78aa6e25edb7dbb1ad89058a4876`（docs-only，`[skip ci]`），其后仅追加 `docs_seal_source` 字段 |

## 2. 新增路径（独占）

- `tests/reader_final_s12/`：`probe.cpp`（C++17）、`api.c`（C11）、`CMakeLists.txt`、
  `fixtures.py`（唯一输入/预期源）、`static_check.py`、`check_s12.py`、`compare_platforms.py`、`strict.py`
- `.github/workflows/reader-final-s12.yml`（只由本分支/本包路径触发，矩阵 `max-parallel: 2`）
- `docs/reader-final-s12/S12-UNICODE-STATE.md`、`docs/reader-final-s12/validation.json`
- `HANDOFF-RESULT.md`（本文件）

## 3. 三轮真实运行（同源证据，未拼接）

| run | 受测 source | 预检 | Windows | Linux | compare | strict |
| --- | --- | --- | --- | --- | --- | --- |
| 40215053846 a1 | `9babde99` | success (job 121234282420) | failure (121234341419) | failure (121234341423) | skipped | skipped |
| 40215267638 a1 | `911db25d` | success (121234927295) | failure (121234974689) | failure (121234974661) | skipped | skipped |
| 40218361806 a1 | `66379633` | success (121244318470) | failure (121244373097) | failure (121244373163) | skipped | skipped |

原工件（未过期，`sha256:` 为 GitHub 记录的 ZIP 摘要；工件内证据由 `strict.py` 逐字节复算，
但 strict 作业从未运行过，所以下列摘要只作为"原工件身份"引用，不构成通过证据）：

| run | 工件 | id | 字节 | digest | 到期 |
| --- | --- | --- | --- | --- | --- |
| 40215053846 | source | 12607480605 | 9313 | `sha256:d757b7e5…` | 2027-01-23 |
| 40215053846 | Windows | 12607128109 | 878792 | `sha256:1ea08fed…` | 2027-01-23 |
| 40215053846 | Linux | 12607123184 | 894568 | `sha256:e46fffa8…` | 2027-01-23 |
| 40215267638 | source | 12607455904 | 9312 | `sha256:0682ba6c…` | 2027-01-23 |
| 40215267638 | Windows | 12607163011 | 2041803 | `sha256:e64af2ab…` | 2027-01-23 |
| 40215267638 | Linux | 12607710102 | 1893206 | `sha256:2bebabc0…` | 2027-01-23 |
| 40218361806 | source | 12607994738 | 9912 | `sha256:c0c52b9c…` | 2027-01-23 |
| 40218361806 | Windows | 12608405799 | 2053261 | `sha256:aab085cb…` | 2027-01-23 |
| 40218361806 | Linux | 12608775312 | 1904652 | `sha256:a92b0716…` | 2027-01-23 |

## 4. 第三轮真正验证到了什么

同一 source/run/attempt（`66379633` / 40218361806 / 1），两个宿主都：

- 以 raw 0.2.0 metadata 家族构建并安装 5 个公共包与 2 个消费者成功（这一步前两轮都过不去）；
- 运行出 **167 条 C++ 记录 + 18 条 C 记录**，两个消费者都没有崩溃；
- **6 项字节稳定断言全部通过**：`main.after_seed == main.after_reattach`、
  `main.settled == main.after_reopen`、`main.final == main.settled`、
  `mirror.receive1 == mirror.receive2`、`mirror.receive2 == mirror.after_reopen`、
  `sidecar.staged == sidecar.reopened`（同一宿主上的 SQLite 快照逐字节相等）；
- 只读重开（C 消费者直接读活动库）**没有改变产品库字节**（校验器未报该问题）；
- 账户隔离、原件入口、bootstrap/重放、NFD 原始字节保留、陈旧 head 的 CONFLICT、UTF-16 计数边界这些记录都匹配。

已观测的 `observations.txt` SHA-256：Windows `607ac32f…`、Linux `a1919f68…`（两者不同，
原因见下第 5 节最后一条）；C 观测两平台相同 `0b6d3db2…`。

## 5. 第三轮失败与根因（全部是本包测试工具缺陷，不是 owner 缺陷）

| 现象 | 根因 | 修正（`afceae3a`，未上云） |
| --- | --- | --- |
| `metadata.book5.receive.one/two` 返回 1、created=0 | 竞争修订 ID 写成 34 个十六进制字符，`identifier()` 直接拒绝，导致并发 head 根本没造出来，连带 `metadata.book5.prepare/stage/pending` 及 `metadata.reopen` 的 pending/sidecar 全部偏离（6+2 条） | 改成 32 位小写十六进制 |
| `metadata.book5.bootstrap` 缺 `revision_len` 字段 | 写该记录时漏了字段 | 补上 |
| `metadata.get.book1.bytes` 期望 401、实测 417 | 预期用 Python 字符数而非 UTF-8 字节数（标题含 emoji/重音） | 用 `.encode('utf-8')` |
| 5 条 `c.*` 记录不符 | C 消费者读的是**已改过标题**的活动库（book2 改 NFC、book3 被外部命令改成 "ÜNÏ 书库 v2"），而预期是初始状态 | C 消费者改读 attach 之后冻结的字节副本；校验器另外证明该副本与初始快照一致、活动库仍等于 `main.final` |
| 两平台观测不逐字节相同 | 随机分配的修订 ID 被写进跨平台观测（`metadata.wire.book1`，以及并发失败后泄漏的 `metadata.book5.prepare.head0`） | 把 wire 的 ID/sha/hex 移到平台本地证据，`check_s12.py` 仍在本地按公开命令文档重建整份 wire |

前两轮失败：run 40215053846 是消费者编译缺陷（`stage_book` 少一个参数、`page::size`、字符串引号写错）；
run 40215267638 是容器类型不匹配（`query.ascii` 以 UTF-16 存储、消费者按 ASCII 读）。两轮都留了原日志与工件。

## 6. 需要 root 做什么

1. 在 `codex/reader-fw-s12` 的 `afceae3a`（或其后继）上推一次，让 `.github/workflows/reader-final-s12.yml`
   跑第四轮——本包已按规程用完三轮，不再自行刷运行；
2. 若第四轮只差"随机 ID 泄漏"或"冻结副本"之类的本包问题，按 `validation.json` 的
   `fixes_not_yet_verified` 逐条对照即可；
3. 只有第四轮同一 source/run/attempt 的 `strict` 作业 success，才可把 S12 记为通过；本包不冒领。

## 6a. 复核入口

- 工作流只看本分支与四个路径；`source-preflight` 每轮都 success，可单独用来确认"只改本包路径、owner/SDK 未动"。
- 重放在 Actions 里只依赖 `tests/reader_final_s12/fixtures.py`（唯一输入与预期源）与两个消费者；
  本地不构建、不跑夹具。

## 7. 明确缺口（一律 pending）

- 未跑过的部分：修正后源码的全部检查项、`compare` 与 `strict` 两个作业本身（三轮都被 skip）。
- 六平台 UI / 宿主接线 / 读屏 / 真机：不在本包范围。
- SDK 原件校验、原件导出、真实 WebDAV：未构建 SDK、未起网络。
- 超过宿主路径上限（Windows 260 字节）的深路径只写平台本地证据，不冒充通过。
- 嵌入 NUL：只证明"计数边界拒绝 NUL"与"截断路径不会把无关文件静默变成产品库"，不声称 C 字符串接口能自检 NUL。

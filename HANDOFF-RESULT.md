# HANDOFF-RESULT S08 诊断输出与账号信息泄漏验收

- 状态：**accepted（仅限本包范围，Windows + Linux）**；完整产品授予仍由 root 控制。
- 固定实现起点：0889f7d1e9a537c6c1b05456547e016b26e1cd85
- J21 凭据实现（e2247deb35b52615810508092441922c4e4f7913）已在该起点内，本包未重写它，也未改其原测试。
- 受测 source：**bbba06e345715d404a9b15b8e0b225d00013ad03**
- docs-only 封存提交：见本文件所在提交（只含 docs/reader-final-s08/ 与 HANDOFF-RESULT.md；提交不能自述其 SHA，故在交回消息中给出）。
- 远端分支：origin/codex/reader-fw-s08；未推默认分支、未开 PR、未做 Release/签名。
- 全部构建、测试、夹具生成与工件解析只在 GitHub Actions；本机只读源码/文档、编辑与 Git。

## Run

| 项 | 值 |
| --- | --- |
| workflow | .github/workflows/reader-final-s08.yml（只由本分支与本包新增路径触发，max-parallel=2，concurrency=reader-final-s08） |
| run / attempt | 40215560970 / 1 |
| 结论 | success（guard、两台平台、report 全绿；同源 aggregate accepted=true） |
| URL | https://github.com/NoGod3524/EXReader/actions/runs/40215560970 |

| 作业 | id | 结论 | 实际检查 |
| --- | ---: | --- | --- |
| guard | 121235824739 | success | 32/32：固定起点祖先、冻结 SDK 祖先且受保护树不变、仅新增路径、三个 owner 模块与起点逐字节相同、凭据模块无日志调用、账号/OPDS 无控制台输出、根构建未引入可选模块；聚合器红 action 21/21 |
| platform (windows-2022) | 121235865937 | success | 115/115；检测器 17/17；诊断判定 0 问题；最终扫描 103 文件 / 1,749,157 B / 0 命中 |
| platform (ubuntu-22.04) | 121235865981 | success | 129/129（含锁 collection 与无服务两条 UNAVAILABLE、解锁后无明文）；17/17；最终扫描 103 文件 / 1,119,493 B / 0 命中 |
| report | 121236152169 | success | 三个工件 ZIP 重新算 SHA-256 与 API digest 一致；拒绝重复/越界条目；包内 report.json 的 manifest 与 ZIP 逐文件一致；source/run/attempt/platform/job、检查计数、judge_problems=[]、detector.passed、scan 命中=0 全部核对 |

## 工件（同 run/attempt，全部未过期）

| 工件 | id | 字节 | SHA-256 | 创建 | 到期 |
| --- | ---: | ---: | --- | --- | --- |
| reader-final-s08-guard-40215560970-1 | 12607760331 | 1,138 | aee94e23df053d0cb71f45029db6c564fba1173820756b28b4d59cfbb31751e3 | 2026-10-25T17:15:21Z | 2027-01-23T17:15:13Z |
| reader-final-s08-windows-40215560970-1 | 12607780393 | 12,504 | af83354cec37cb4e6e434f86964726b2fc541de9a3f72d7d6d9847991f70688d | 2026-10-25T17:15:59Z | 2027-01-23T17:15:13Z |
| reader-final-s08-linux-40215560970-1 | 12606794998 | 14,561 | c73a1398f5f0fa918023e318d36e2978b570dc75e112fa0851fe66993a769beb | 2026-10-25T17:16:30Z | 2027-01-23T17:15:13Z |
| reader-final-s08-report-40215560970-1 | 12607640840 | 1,424 | f35dfaee75368719207a7632811c541e7e1588efac61ecbff505babdd8702a67 | 2026-10-25T17:16:44Z | 2027-01-23T17:15:13Z |

API 的 digest 与 report 作业重新计算的 ZIP SHA-256 逐项一致。**程序 hash**（消费者二进制 consumer.sha256、两个安装前缀下每个文件的 path/bytes/sha256）记录在两个平台工件内的 report.json，并由 report 作业按 manifest 逐文件核对；按共同约束本机不下载/解压工件，故此处不复制这些值。

## 实际检查项

| 阶段 | Windows | Linux | 内容 |
| --- | --- | --- | --- |
| opds | 34/34 | 34/34 | 正常下载、401、500、传输中断、跨源 302 丢凭据、redact 契约/截断/超长；请求行保留 GET/来源/路径/状态与非秘密参数，userinfo 与 token 值消失 |
| credentials | 27/27 | 27/27 | 空存储、精确回读、更短值更新无残留、账号与 namespace 隔离、缓冲区不足、非法 ID/namespace、0 长度、NUL 二进制、Unicode、2048 上限、删除与重复删除、状态名稳定 |
| profiles | 36/36 | 36/36 | 空存储、三条隔离档案、两阶段激活、userinfo/query 拒绝、非法 UUID/名字/相对 store、load(NULL)、公开 cancel 回调（首次轮询与提交前）CANCELLED 且文档哈希不变/无 .tmp、VERSION/FORMAT 的 offset、IO 的 system_error、32 条上限、rename/remove 只删记录 |
| worker | 4/4 | 4/4 | 独立子进程写入档案与凭据后退出；父进程在退出后立即扫描 store、临时 HOME 与日志（0 命中） |
| reopen | 6/6 | 6/6 | 新进程读回持久档案与凭据，账号隔离仍成立 |
| unavailable | — | 6/6 + 6/6 | 锁默认 collection、无会话总线两条真实 UNAVAILABLE；解锁后专用账号仍 NOT_FOUND（没有写入任何明文） |
| cleanup / verify-clean | 5/5 + 3/3 | 5/5 + 3/3 | 只删本 job 自己的记录，随后空存储与凭据消失 |

红 action（每个平台各自、用本次真实秘密）：planted 的 raw/32 字节窗口/hex/HEX/base64/base64url/percent/UTF-16 必须检出（12 例），干净文件必须 0 命中；空消息、只有 REDACTED、携带 forbidden 文本的诊断必须被拒，形状正确的诊断必须被接受（4 例）。聚合器另有 21 例合成正反例（digest 不符、ZIP 越界/重复/多余成员、manifest 改字节、source/attempt/platform/检查计数造假、过期工件、作业结论失败等）。

## 保留的失败（原 run/attempt 与根因，未删改）

| run | source | 结论 | 根因（全部在本包新工具内） | 修复于 |
| --- | --- | --- | --- | --- |
| 40214797350 | fa7455f8 | failure（guard） | 冻结 SDK 树 diff 取自冻结提交而非本包起点（主线 CMakeLists 历史不属本包改动）；检测器正控制极性反了 | 6c54b8de |
| 40214912182 | 6c54b8de | failure（两台平台 + report；Windows 113/115，Linux 128/129） | Linux 调用了 verify-clean 而非 verify-unavailable-clean；OPDS 请求行诊断复用了模块状态名 http，判分读到 code 8 与 http_status 500 不一致；Windows 用文本模式写 VERSION/FORMAT 夹具，CRLF 破坏规范形状 | febc2ebd |
| 40215199931 | febc2ebd | failure（未进入消费者） | 一次编辑把裸注释行插进 runner.py（第 129 行 IndentationError）；聚合器同时读了未定义的 job 变量（report 作业尚未走到） | bbba06e3 |

三轮失败均为本包新增脚本/夹具的缺陷，未发现 owner 模块缺陷，未降低任何断言；第四轮在同一断言集上全绿。这超出名义三轮预算，已在 validation.json 的 rounds_used/rounds_note 中如实记录；未删除任何失败工件。

## 未验证 / pending

- **Windows Credential Manager UNAVAILABLE**：本 job 未诱发。J21 已记录低完整性进程、停止 VaultSvc、S4U 计划任务三种尝试都不成立，本包不重复猜测、不据此授予。
- **macOS / iOS / Android 凭据后端**：本包不重跑；只引用 J21 原 run40057087875 与其严格复核 run40060725476，不重新授予。
- 真机、读屏、性能预算不在本包范围。

## 复现

```bash
python3 tests/reader_final_s08/check_aggregate.py
python3 tests/reader_final_s08/guard.py --output build/s08-guard
# 平台作业在 Actions 内构建三个 owner 模块并安装，再编译 tests/reader_final_s08/consumer，然后：
python3 tests/reader_final_s08/runner.py --platform linux \
  --consumer build/s08/consumer/reader-final-s08-consumer \
  --credentials-prefix build/s08/cred-stage --profiles-prefix build/s08/profiles-stage \
  --output build/s08/evidence --scan build/s08/build-logs
python3 tests/reader_final_s08/aggregate.py --downloads build/s08-zips --output build/s08-report
```

结论细节与逐项证据见 [docs/reader-final-s08/validation.json](docs/reader-final-s08/validation.json)。

# C02 完整攻坚交接：Windows 原生持久 CAS Journal

更新时间：2026-10-31 UTC  
仓库：`NoGod3524/EXReader`  
正式验收：**95/108，未改变**

> 本文件是技术交接，不是新源码写入或 CI 授权。用户本次要求将 C02 完整交给另一智能体攻坚，不能据此认定旧写入拒绝已解除。接手先只读核实，再经正式审批路径处理受拒操作；不得换代理、路线、命令或工作树绕过拒绝。

## 1. 任务目标与当前结论

C02 要将已有协调器的 journal append 抽象，落实为真实 Windows/NTFS 原生持久事务后端，能够拒绝：
- 调用方旧 tip、非空 store 上的 count-zero 启动；
- 磁盘全链、namespace、identity 或 intent 损坏；
- 部分写入、flush/readback 失败和崩溃中间态；
- 丢失或过期的 live domain capability。

事务必须在同一保护范围内完成：
1. 获取并持有不可撤销的 live exclusive domain borrow。
2. 验证真实磁盘全链、intent、文件身份及调用方 **exact expected tip**。
3. 完全匹配后才 append。
4. 持久化并独立回读。
5. 确定成功才返回新 tip。

**当前不是“只差最后一次测试”。** 原生包只落地两个未提交文件，C 文件在 `if(s` 截断；其余五个预期文件不存在。

ABI3 的新 **16 cases / 64 checks** 是内存合同测试，不是原生持久性证明。旧 ABI2 **81 checks / 6 failures** 仍保留，ABI3 run 整体为 failure。

即使完成原生 journal 候选，也不能直接宣称完整 P0：真实 host/SDK/source 借用生命周期、持久 gate owner、可信 provenance、publisher/recovery/observer/fault 接线仍需分别证明。

## 2. 指定通路与禁止事项

### 唯一 SOURCE/Git/docs 执行通路

所有 SOURCE、Git、docs 读取及另行获准的修改，均通过：
- Desktop Commander 设备：`lap25002`
- deviceId：`d55d0477-84bb-4425-8708-5a3ecacce78b`
- 已正常登录 CLI：

```text
npx --yes instabox@0.8.52 exec m_agqxv2s72g5vwdtsifu5cnmml4 --json --cwd <既有tree> -- <命令>
```

不得通过 GitHub connector、浏览器、其他机器或本地 checkout 另读/另写源码绕过该路线。**纯 GitHub CI 元信息允许使用只读 connector**；这不授权通过 connector 读取 SOURCE/Git/docs 或执行仓库修改。本交接中的 Actions 元数据核验实际使用上述通路内正常登录的 gh。

### 构建与测试
- 构建、语法检查、测试、产品执行：**仅获准 Actions**。
- 不在本地做“快速编译”“仅语法检查”或产品运行。
- 本交接轮次不下载、解析 artifact ZIP。
- Git 状态、文本、文件长度、SHA256、Actions 元数据和日志可只读核实。
- 不读凭据，不重启机器，不启动 Codex。

### 冻结范围
- C01：`ccd7fec67eb8aa463b09533ce320820f2da472d9`
- SDK pin：`8357eafa28423a7ab93ba08b823af80f01ad1505`
- 不改生产 owner、SDK、主线路由、旧测试及旧断言/预算。
- 不推主线，不开/合 PR，不打标签，不发布。
- 不擅自增加共享额度任务或 CI 轮次。
- 保留旧红结果、失败日志及证据，不能删 fail、改期望或降检查数。
- Apple、Claude H01/H02、F12 六包材料审计属于其他 writer 范围，不接管其树或文件。

## 3. 第一条可执行只读命令

通过指定设备的 Desktop Commander start_process：

```powershell
npx --yes instabox@0.8.52 exec m_agqxv2s72g5vwdtsifu5cnmml4 --json --cwd /data/workspace/exreader-dot-c02-native-journal-20261030 -- git status --short --branch --untracked-files=all
```

随后只读核对 HEAD、两个 partial 文件长度/哈希、七路径存在情况、是否有其他 writer 或未知进行中操作。

工具返回 PID/call_id 时，应读取原操作结果，不重复提交结果不明的命令。状态若与本交接不同，先查明，不覆盖、不 reset。

## 4. ABI2 → ordering → ABI3 证据链

以下四个 run 的 source、branch、attempt=1、终态，已于 2026-10-31 经指定 CLI 的 GitHub API 核实。细分检查数来自保留的历史证据摘要；本轮没有解包 artifact 重算。

| 阶段 | Source | Branch | 证据 |
|---|---|---|---|
| ABI2 hardening 基线 | `b830486c21bfa82cf69a1d816b424fe2fc53d29b` | `codex/windows-coordinator-hardening-20261030` | [41128388018](https://github.com/NoGod3524/EXReader/actions/runs/41128388018)：双平台各61 checks / 15 cases，success；engine_mock_only |
| 追加回归 | `27ca2f173eaed91dac35ab198723b3387bbaedac` | `codex/dot-c02-regressions-20261030` | [41133306330](https://github.com/NoGod3524/EXReader/actions/runs/41133306330)：双平台各81 checks / 9 failures，failure |
| custody ordering 修复 | `1f0444b32e5b13c1a004383a8350cca8519248c3` | `codex/dot-c02-ordering-fix-20261030` | [41134698093](https://github.com/NoGod3524/EXReader/actions/runs/41134698093)：双平台各81 checks / 6 failures，failure；前三个顺序问题修掉 |
| additive ABI3 合同 | `a8d0b162d8c21617e4c2c837e3eb2b2174bbf69b` | `codex/dot-c02-cas-contract-20261030` | [41137923896](https://github.com/NoGod3524/EXReader/actions/runs/41137923896)：新16 cases / 64 checks绿；旧81/6红保留，整体failure |

### 既有工作树

```text
/data/workspace/exreader-windows-coordinator-hardening-20261030
/data/workspace/exreader-dot-c02-regressions-20261030
/data/workspace/exreader-dot-c02-ordering-fix-20261030
/data/workspace/exreader-dot-c02-cas-contract-20261030
/data/workspace/exreader-dot-c02-native-journal-20261030
```

当前 native：

```text
branch: codex/dot-c02-native-journal-20261030
HEAD:   a8d0b162d8c21617e4c2c837e3eb2b2174bbf69b
```

### 关键已提交路径

ABI2：

```text
extras/migration/windows_coordinator_hardening_20261030/
tests/migration/windows_coordinator_hardening_20261030/wh_test.c
.github/workflows/dot-c02-regressions-20261030.yml
.github/workflows/dot-c02-ordering-fix-20261030.yml
```

ABI3：

```text
extras/migration/windows_coordinator_cas_20261030/CMakeLists.txt
extras/migration/windows_coordinator_cas_20261030/include/exr_wh3.h
extras/migration/windows_coordinator_cas_20261030/src/wh3_core.c
tests/migration/windows_coordinator_cas_20261030/CMakeLists.txt
tests/migration/windows_coordinator_cas_20261030/wh3_test.c
.github/workflows/dot-c02-cas-contract-20261030.yml
```

早期历史文档：`docs/reader-total-progress/CLAUDE_DOT_C02_20261030.md`。
该文档的 wc_* 与 reference filesystem provider 是早期模块说明，不能替代后续 wh_* / wh3_* 合同。

### ABI3 工件摘要

Windows：

```text
artifact ID: 13016639070
bytes:       1215
SHA256:      bf604c4c14dc6dd7da93a19f6933037732112bdca1a0aed2e7acaafd161f8ec8
```

Ubuntu：

```text
artifact ID: 13016539351
bytes:       1208
SHA256:      0c2f2f56e833a46e67e9048bff4ed4ae8c74f39c6bfc57d280c8960b9023e452
```

入口：[ABI3 run artifacts](https://github.com/NoGod3524/EXReader/actions/runs/41137923896)。上述工件信息为保留摘要，本轮未下载重算。

## 5. 当前 native partial 的精确状态

2026-10-31 00:07–00:08 UTC，指定 CLI 只读核实：

| 文件 | 状态 |
|---|---|
| include/exr_wh3_win.h | 未跟踪，1694 bytes |
| src/wh3_win.c | 未跟踪，8400 bytes，截断 |

完整哈希：

```text
de93266dae6fbf3e62f4cba9822331884b9b376a26e3cd29482818ff70515f34
extras/migration/windows_coordinator_native_journal_20261030/include/exr_wh3_win.h

e273a27b33646b2776c89057b0c85413bd1d86cf883df005d0ee5418dc7114c5
extras/migration/windows_coordinator_native_journal_20261030/src/wh3_win.c
```

C 文件末尾：

```c
if(!s||!cap||!expected||!line||!after)return result;
EnterCriticalSection(&s->lock);
if(s
```

不是完整实现，不能声称已可编译或 append 已完成。

### 精确七路径

1. `extras/migration/windows_coordinator_native_journal_20261030/CMakeLists.txt` — **不存在**
2. `extras/migration/windows_coordinator_native_journal_20261030/include/exr_wh3_win.h` — **1694B partial**
3. `extras/migration/windows_coordinator_native_journal_20261030/src/wh3_win.c` — **8400B partial**
4. `tests/migration/windows_coordinator_native_journal_20261030/CMakeLists.txt` — **不存在**
5. `tests/migration/windows_coordinator_native_journal_20261030/wh3_win_test.c` — **不存在**
6. `.github/workflows/dot-c02-native-journal-20261030.yml` — **不存在**
7. `docs/reader-total-progress/DOT_C02_NATIVE_JOURNAL_CANDIDATE_20261030.md` — **不存在**

旧 writer 的完整草案可能仅在其临时 functions store 中，不能保证恢复。以当前磁盘 partial 为事实，不宣称七文件齐备。
不得删除、覆盖、reset 或另建替代树来规避旧受拒写入。

## 6. ABI3 的硬合同

exr_wh3.h 定义：
- wh3_tip 包含 manifest SHA256、line_count、**完整最后 canonical line** 的 SHA256，不是 ABI2 body seal。
- count=0 必须对应真实空 store；last_line_sha 是64个ASCII零。
- backend 在一个保护事务里验证 live cap、磁盘全链与 exact expected tip，再 append/persist/independent readback。
- WH3_TX_MISMATCH 保证无 append。
- WH3_TX_UNCERTAIN 可能已经写入。
- 两种失败均不允许 facade release。
- session 调用必须串行，backend 还必须串行化共享存储。
- facade 不提供原生存储、Windows 锁或 SDK admission。

wh3_core.c 当前行为：
- acquire/reacquire 捕获 cap；check 要求同一个 cap。
- append3 将 expected 交给 backend。
- 只有 OK 且 actual tip 每字段等于 desired，才推进 expected。
- backend 报 OK 但 tip 不符，仍转 UNCERTAIN。
- recover 验证调用方 prefix，再建立 expected；真正磁盘 exact-CAS 仍是 backend 责任。
- dispose 服从原 core 的持有/拒绝释放规则，不能以 free 代替失败所有权处理。

## 7. Native partial 已有内容与必须处理的漏洞

### 已有但未经原生验收

existing local fixed-drive NTFS root；固定journal.bin/intent.bin，不创建、截断、修复；trusted root/journal/intent的volume64+FileID128；初始reparse、类型错误、多hardlink拒绝；ancestor deny-delete pins；journal/intent以READ|WRITE、share READ打开；store内CRITICAL_SECTION；journal长度帧与canonical lines；intent固定424B、前360B计算seal及BEGIN/ACK链；enter/validate/poison/leave回调。

**这些回调是合同，不是冻结C01或生产owner实现。**

### 当前必须修复或明确的点

1. **append未完成。** 局部变量和函数签名不是事务实现。
2. **空intent漏检。** `if(pending||(z&&count!=j->n))` 在 z=0 时允许非空journal避开覆盖数比较。
3. **BEGIN old未绑定上一ACK count。** 可能遗漏或重复覆盖；须同时约束seq、old/count、BEGIN/ACK及全journal覆盖。
4. **canonical保留字段不足。** seal正确不代表任意保留字节合法；类型、版本、保留零字节、格式和类型专属字段须检查。
5. **open未读全journal/intent。** 当前open成功仅证明句柄/部分namespace，不证明可恢复状态。必须在open或使用前强制完整验证，不能隐式放行。
6. **原prefix绑定不足。** GetFinalPathNameByHandle再重开只证明当前final path，不独立证明原调用路径未改绑。须结合原prefix、全部ancestor pins、trusted root检查。
7. **目录metadata不是永久冻结。** share READ|WRITE不能证明reparse/metadata不可变；OS未阻止的变化须在下一写前重验拒绝。
8. **j/i同文件双路径。** 两者identity必须不同，不能只认文件名。
9. **独立回读不能用内存值代替。** 明确回读句柄来源、身份检查、flush/readback错误分类。
10. **UNCERTAIN不是内存poison即可闭合。** bool、回调名或活句柄均不证明新进程仍被隔离；close不等于CLEAN。
11. **有限预算不得静默扩大。** REC=424、MAX_PINS=64、EXR_WH_MAX_JOURNAL等边界应显式拒绝。
12. **cap必须覆盖整个事务。** enter至leave期间不能被撤销/换代穿插；写后失败不能降格为无写MISMATCH。

上述为静态审查与合同要求，本轮没有执行故障复现或本地测试。

## 8. 必须覆盖的确定性测试

测试只能在批准的Actions中进行，使用真实Windows文件、句柄、独立进程和显式握手。

### A. 无写失败/CAS

覆盖非空store+count0、调用方旧prefix、backend实际tip更晚、manifest不符、journal内部/尾部损坏、错长度/断帧、intent空/漏项/重复/错序/错hash。

每个MISMATCH必须证明journal、intent前后长度和完整字节哈希不变，无provider mutation/release，不自动更新expected再重试，不截尾、不修复、不清pending。

### B. BEGIN → journal → ACK 崩溃切点

每个切点都应明确：发生过什么写入、flush状态、返回码、持有对象及新进程观察。

1. PRE_BEGIN，无写；
2. BEGIN prefix；
3. BEGIN完整写、flush前后；
4. journal长度头prefix；
5. journal payload prefix；
6. journal完整写、flush前后；
7. independent readback失败或错误内容；
8. ACK prefix；
9. ACK完整写、flush前后；
10. ACK_FLUSHED但函数尚未返回。

现有phase只有PRE_BEGIN、BEGIN_FLUSHED、JOURNAL_WRITTEN、JOURNAL_FLUSHED、ACK_FLUSHED。
现有fault只有SHORT_WRITE、FLUSH_FAIL、READBACK_FAIL。
不足以直接声称BEGIN/ACK prefix已覆盖；必须明确fault作用于哪一次I/O。

可能写入的失败必须UNCERTAIN并保留证据。新进程拒绝dangling BEGIN、缺ACK、断帧、错序、错hash及覆盖缺口。
ACK已flush、返回丢失时磁盘可能已完成，但旧expected仍不能自动升级。
**注入flush API失败不等于物理断电耐久性证明。**

### C. Namespace和句柄生命周期

- A open持有后，B尝试writer、rename、逐级ancestor/file DELETE。
- 初始hardlink/reparse、错误trusted identity、同文件j/i拒绝。
- pin后新增hardlink/reparse，若OS未阻止，下一写前重验拒绝。
- 不把“目录非空导致FSCTL失败”误当sharing保证。
- 原路径改绑、祖先替换使用确定性barrier。
- clean close后能重新open，避免永久泄漏。
- UNCERTAIN后是否释放必须由真实持久domain隔离合同保证，不靠任意free。

### D. 回归账本

旧ABI2 81 checks / 6 failures保留；ABI3原16/64保留；新native用例独立计数和receipt。
Linux合同job不能把未执行的Win32行为标为原生PASS。
不通过修改旧测试来“消除”旧6fail。

## 9. 真正的 gate owner 接线

完整P0还须独立证明：
- trusted domain→lease identity的可信来源；
- pending/quarantine何时持久化；
- 所有真实host、SDK、source open入口查询同一门闩；
- source借用期间cap、文件及库owner保持活性；
- 异步读取、错误撤销、close、restart顺序；
- publisher真实exclusive custody与磁盘publication inspect；
- recovery合法phase及observer/fault证据；
- 不确定后拒绝新admission，进程死亡后仍拒绝；
- 只有合法且独立验证的提交才能清pending、推进generation。

不得用mock provider、空poison回调、打印常量sdk_open_attempts=0或shape-valid tuple替代这些证明。
修改冻结C01或生产owner需要独立任务与明确授权，不在当前七路径内。

## 10. H01与Restart边界

### H01

```text
branch: codex/claude-h01-domain-gate-20261030
source: 559f55aa76bb9f1435a5541460abfc233e090f56
doc:    0d33b0a94797f78f275220ca1a1480de9fc6b167
run:    41144247183
```

[证据run](https://github.com/NoGod3524/EXReader/actions/runs/41144247183)

31例纯Python，仅检查binding/registry形状及映射一致性。未证明可信provenance、真实80B lease header、lm_rr_open接线、Windows行为或SDK admission。
不能把BINDING_VALID当成清门闩资格。

### 既有Restart 26例

```text
branch: codex/p0-win-restart-reader-20261030
source: 6db7c3dc1005c7fd22f91b02a150bfdd671f723c
doc:    638976413692412fd7cc15d7e508d0382d1faffd
run:    41130069225
```

[证据run](https://github.com/NoGod3524/EXReader/actions/runs/41130069225)
这是分类候选，不是COMMIT、SDK准入或完整P0。

### 新Restart局部修复已完成，不要重复实现

```text
branch: codex/p0-win-restart-window-lock-20261030
tree:   /data/workspace/exreader-dot-p0-restart-window-lock-20261030
source: 43f2fd0f94cb820a4ed42ca99ab0906272ba8623
doc:    052fb26b7ed47399b15f968bc00b7885fb4568bb
run:    41146675121, attempt1, success
```

- [验证run](https://github.com/NoGod3524/EXReader/actions/runs/41146675121)
- [封存结果](https://github.com/NoGod3524/EXReader/blob/052fb26b7ed47399b15f968bc00b7885fb4568bb/docs/MIGRATION-WINDOWS-RESTART-WINDOW-LOCK-20261030.md)

修复内容：acquire EXCLUSIVE成功后，首次lease_window失败返回持有E的REFUSED对象，不再提前close。
原26+独立新2通过；生产无新增测试hook，专用编译宏和双map验证通过。

- A：helper解锁后活对象shared status2；显式close后status3 STALE，新reader成功。
- **B残余：**磁盘generation5/PENDING0；活对象shared status2；kill后shared实测 **status0、stale=false**，新reader只是因generation拒绝。

因此，一个reader拒绝不等于全部SDK/readers在崩溃后仍被隔离。

```text
artifact ID: 13021382398
bytes:       597584
GitHub ZIP SHA256:
14feee6642fe5e4bcff17ccba738cd8d7ebedeb0872efb9904cf6d03a41343a8
```

本轮未下载或解析ZIP。

## 11. 旧拒绝：已知与缺失

已知历史摘要：
- 旧writer：`/root/audit_c02_integration_safety`。
- 约2026-10-30 22:55，存在具体“七路径+一次双job run”的授权摘要。
- 随后core 8400B→9100B追加仍被审批拒绝。
- 摘要称拒绝理由认为scope未明确。
- 当前文件仍8400B、末尾if(s。
- 本接手者只读，没有执行或重试该写入。

**目前缺失：**原denial工具call ID、完整命令和action、审批理由逐字原文、原操作完整execution status、拒绝属于何种权限/政策类别。

不能编造这些内容。当前长度一致也不能替代原操作未执行证明。
用户询问“谁负责”不是新写权限；之后要求handoff仅授权交接，不能据此解除native写入拒绝或增加CI轮次。

### 正式恢复所需步骤

1. root或原审批记录提供原action、target、reason、execution status，能够取得则原样保留。
2. 若无法取得，向正式审批路径明确提交“原记录缺失”的事实、七路径、branch/tree、before-image长度/hash、恢复partial目的、排除范围及一次双job计划，请求对**该受拒操作**的具体处置。
3. 不再泛泛询问yes；也不能靠用户确认覆写不可解除的policy restriction。
4. 仅在确认未执行、有实质新相关证据且符合正式重试条件时，至多一次限定重试。
5. 再拒即停止，不能换命令、代理、路线或工作树继续。
6. uncertain先检查原operation和文件，不重复写。

## 12. 有界实施计划

以下均以所需批准已落实为前提。

**阶段0：只读接手。** 核HEAD、dirty、七路径、hash、旧run；取得或明确缺失的拒绝记录；确认唯一writer。

**阶段1：设计复核。** 形成状态转移表、MISMATCH/UNCERTAIN分类、domain borrow和cleanup条件、每个crash cut真实验收、independent readback与namespace证明方案。先独立review，不先本地试编译。

**阶段2：限定七路径实现。** 保留partial来源，完成native候选、安装/消费者CMake、独立测试、新workflow、证据文档。不顺手改旧ABI2测试、C01、SDK或生产owner。

**阶段3：提交前只读审查。** 检查路径guard、pins、旧断言不变、真实Win32调用、确定性握手、hooks范围及receipt字段。

**阶段4：一次有界Actions。**
- 仅批准的一次双job run。
- 明确Windows原生与另一job合同的证据范围。
- push触发、dispatch二选一，不能双启动。
- 旧授权的一次run额度不能默认仍可用。
- 不自行获得无限repair-push或重跑权限。

**阶段5：跟到终态。** 绑定source/run/attempt/job/artifact。失败保留日志与partial输出；缺少新增轮次授权则停止运行，提交精确失败点和最小下一包。

**阶段6：独立结果审查与封存。** 记录候选通过项、旧6fail和真实gate剩余。不得自行提高95/108，不合PR、不发版。

## 13. 最终交付清单

接手agent至少返回：
- 精确branch/tree/base/source/document SHA；
- 七路径改动清单及冻结范围diff证明；
- 各run/attempt/job终态；
- 旧61/81、新16/64与native用例计数的区别；
- 每个切点写入、flush、返回码、cap/句柄状态；
- 重启后真实shared/SDK准入测量；
- 原始失败保留位置及artifact metadata/digest；
- 工件读取证据层级：API元数据、日志、还是确实读取过内容；
- C01、SDK、生产owner、旧测试是否未改；
- blocked action/target/reason，以及completed/denied/pending/uncertain分类；
- 下一步需要哪个owner与哪项具体授权。

**不要把文档完整、mock通过或分类器拒绝，写成原生持久隔离或完整产品验收完成。**

## 14. 存档说明

本交接存档路径：`docs/reader-total-progress/C02_FULL_ASSAULT_HANDOFF_20261031.md`。
保存于独立receipt文档分支`codex/dot-apple-receipt-20261030`，不保存到native dirty tree。
本次仅交接文档，未续写native partial，未执行构建/测试，未启动CI，也未解除原受拒操作。
独立文档工作树内既有Apple handoff的未提交修改不属于本次提交。

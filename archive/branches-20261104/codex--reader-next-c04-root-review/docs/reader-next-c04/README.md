# C04 真实 RTF 兼容性候选

起点 `e67d87cb`，目标 SDK 源码 `edddc463`（批准的 3.41），F5 固定源码 `278d6369`。
本包只交 `candidates/reader-next-c04/rtf-root-tail-padding.patch`：对 `src/rtf.c` 的单文件补丁，
CI 在 `edddc463` 的隔离副本上应用；本分支 `src/include` 与批准 SDK 逐树相同，不被改写。
补丁产物是**未接纳候选**，不是批准 SDK。

## 方法

1. 原始字节：由 F5 清单（不改文件、查询、预期）下载两份真实 RTF（63797B / 36814B），
   核对字节数与 SHA-256，再由 F5 消费者经安装后的公开 SDK 导入、读回、打开、分页、
   首/中/末页、查找、锚点捕获/解析、重开。
2. 根因：`rtf_scan.py` 只读字节调查（括号、根组之后的字节、NUL、参数范围、`\bin`、`\u`、`\'`、代码页），
   与 `diag_instrument.py` 生成的诊断副本（每个 `goto done` 报告源码行与流偏移）互证；
   诊断副本只在 diagnose 作业构建，不是候选，也不安装。
3. 候选：根组关闭后只接受 NUL 与 CR/LF/空格/制表补白；其他尾部字节、第二个根组、多余 `}`、
   截断、整数溢出、非法 `\bin`、`\'00`、`\u` 越界及非 1252 代码页保持 `EXR_FORMAT` 且不产生文档。
   字体编号接受 0..32767，分配/读取/提交/释放使用同一上界；字体名仍受原 64 MiB 元数据预算与单名上界约束，指针表固定为 32768 项（64 位约 256 KiB）。
   对真实 Word 流使用的保留 `listid=-1..-5` 增加只读兼容扩展：保留 signed int32 原值，按精确相等查找；不取绝对值、不偏移、不作为数组索引。`ls` 仍为独立的 1..2000 索引，重复定义、重复 override、数值溢出仍拒绝；新增无定义且无显式 listtext 回退时的拒绝测试。此扩展偏离微软 RTF 规范的保留值要求，不称为规范原本允许。
4. 回归：候选 SDK 全量 ctest（含原 `native-rtf*`），以及安装后公开 API 的边界测试
   `test_rtf_real_boundary.c`（保留原补白/坏流测试，增加字体上边界与重复定义、signed ID 0/-1..-5/INT_MIN/INT_MAX、正负不碰撞与无效引用）。
5. 前后对照：同一 F5 消费者分别对未改 SDK 与候选 SDK 运行，保存原失败与补丁后结果。

## root 审查

轻量 run `40233612001` 在 Actions 下载并认证两轮历史 ZIP，区分 base/candidate 的边界与全量 ctest：候选两轮两平台均退出 0；旧正式 F5 wrapper 误传相对路径，导致两种 SDK 都返回 Cannot open file，不能据此授予或否定候选。

run `40234148787` 重新下载两份固定原件并扫描控制词：Crowley 的定义 `listid=-2` 位于字节 10239，override 同值位于 13058，绑定 `ls2`（13289），正文在 29936 及后续实际引用；另一列表 `1358776223` 绑定 `ls1`。不是未使用占位。冻结 SDK 已有 INT_MIN 列表成功回归，未改任何 frozen 断言。

root wrapper 将原件、消费者、字体与结果路径明确转为绝对路径，另用安装后的公开 API 对原件记录数值状态：base 必须为 `EXR_FORMAT`（5）且无文档，candidate 必须 `EXR_OK`（0）且有文档。F5 消费者与完整预期不改。严格汇总认证本轮四个上游作业、source/run/attempt 与四个原 ZIP 的 digest/bytes/expiry，并逐项比对下载工件的原字节。

规范来源：[Microsoft RTF 1.9.1 原文](https://interoperability.blob.core.windows.net/files/Archive_References/%5BMSFT-RTF%5D.pdf)（[美国国会图书馆的原文入口](https://www.loc.gov/preservation/digital/formats/fdd/fdd000473.shtml)）；微软旧 1.6 Header 链接现已重定向，规范镜像也保留了 -1..-5 reserved 条文。

root 完整 run `40234424624` 两平台各 169/169 原 SDK 回归与 100 项边界通过，Micro 原 F5 全过；Crowley 原查询 miss 导致本轮整体失败。公开正文诊断 `40235597650` 证明原查询不在实际正文，保留原 F5 失败。详见 [root-review-validation.json](root-review-validation.json) 和独立 [新版清单提案](F5-MANIFEST-CORRECTION-PROPOSAL.md)。本候选始终 `accepted:false`。

## 性能

不凭单轮耗时宣称预算达标；`compare.json` 的耗时只是单次观察。

## 状态

见 `HANDOFF-RESULT-C04.md`。

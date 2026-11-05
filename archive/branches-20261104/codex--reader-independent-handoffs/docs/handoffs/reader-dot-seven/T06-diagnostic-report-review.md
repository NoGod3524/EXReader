# T06：用户诊断导出隐私与故障复审

先读[本批共同约束](README.md)，再读[原J21完整任务](../reader-next-wave/diagnostic-report.md)。本包是交回后的独立复审/必要修复，原任务的完整目标和验收继续有效，不从头重做。

- 固定起点：`4793224343950b279a3591c8398f5a2a8514d754`
- 原交付分支（只读）：`codex/reader-diagnostic-report`
- 新的唯一写入分支：`codex/dot-diagnostic-report-review`
- 允许修改的全部路径：

- `apps/reader/diagnostic-report/**`
- `tests/reader_diagnostic_report/**`
- `.github/workflows/reader-diagnostic-report.yml`
- `docs/READER-DIAGNOSTIC-REPORT.md`
- `docs/validation/reader-diagnostic-report.json`

## 本轮必须完成

核凭据、Authorization、URLuserinfo/query、本地绝对路径、书名/正文/标注正文及嵌套错误消息的隐私边界；白名单字段、严格限额、坏UTF-8/控制符/截断、取消、失败原子性及并发快照。真实注入测试秘密并扫描全部输出，不能只grep几个生产字符串。

读原文档/验收JSON，云端API核实受测source、真实run/作业/工件；比较交回HEAD与tested source差异。沿真实调用流复核输入、输出、错误、取消、提交和释放，不能仅抄上一位agent的总结。

对确认缺陷补最小实现与可执行负例，保留原用例和本包原平台范围。原strict若缺真实job认证、唯一ZIP成员或二进制身份，补齐相应拒绝例。若仅语义或证据缺口，明确限定，不制造功能通过；不能越权改共享模块来让测试通过。

原代码无缺陷且原证据足够时，交一份定向复核结论并保留原受测身份即可。任何源码/测试/工作流修改后，按本包原平台真正执行新source；证据只归该source。完成和交回格式见共同约束。

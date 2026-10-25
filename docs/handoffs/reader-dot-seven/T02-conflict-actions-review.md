# T02：显式冲突处理复审与修复

先读[本批共同约束](README.md)，再读[原J11完整任务](../reader-next-wave/explicit-conflict-actions.md)。本包是交回后的独立复审/必要修复，原任务的完整目标和验收继续有效，不从头重做。

- 固定起点：`37fdc830d75eee8590120d52d4d881102e0d9dc4`
- 原交付分支（只读）：`codex/reader-explicit-conflict-actions`
- 新的唯一写入分支：`codex/dot-conflict-actions-review`
- 允许修改的全部路径：

- `apps/reader/conflict-actions/**`
- `tests/reader_explicit_conflict_actions/**`
- `.github/workflows/reader-explicit-conflict-actions.yml`
- `docs/READER-EXPLICIT-CONFLICT-ACTIONS.md`
- `docs/validation/reader-explicit-conflict-actions.json`

## 本轮必须完成

检查完整并发头、prepare到commit之间外来修订、墓碑/restore依赖、稳定重试ID及历史/outbox不重复。至少真实两端并发、缺父补回、过期快照拒绝；reading anchor仅展示，不能猜测resolve或按时钟选胜者。

读原文档/验收JSON，云端API核实受测source、真实run/作业/工件；比较交回HEAD与tested source差异。沿真实调用流复核输入、输出、错误、取消、提交和释放，不能仅抄上一位agent的总结。

对确认缺陷补最小实现与可执行负例，保留原用例和本包原平台范围。原strict若缺真实job认证、唯一ZIP成员或二进制身份，补齐相应拒绝例。若仅语义或证据缺口，明确限定，不制造功能通过；不能越权改共享模块来让测试通过。

原代码无缺陷且原证据足够时，交一份定向复核结论并保留原受测身份即可。任何源码/测试/工作流修改后，按本包原平台真正执行新source；证据只归该source。完成和交回格式见共同约束。

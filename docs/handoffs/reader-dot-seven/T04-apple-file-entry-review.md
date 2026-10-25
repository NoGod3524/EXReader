# T04：Apple 文件入口复审与修复

先读[本批共同约束](README.md)，再读[原J05完整任务](../reader-next-wave/apple-file-entry.md)。本包是交回后的独立复审/必要修复，原任务的完整目标和验收继续有效，不从头重做。

- 固定起点：`3c355b4ea3faab974861f4863893c6018653740c`
- 原交付分支（只读）：`codex/reader-apple-file-entry`
- 新的唯一写入分支：`codex/dot-apple-file-entry-review`
- 允许修改的全部路径：

- `extras/apple-file-entry/**`
- `tests/reader_apple_file_entry/**`
- `.github/workflows/reader-apple-file-entry.yml`
- `docs/READER-APPLE-FILE-ENTRY.md`
- `docs/validation/reader-apple-file-entry.json`

## 本轮必须完成

核文件选择/安全作用域/协调读写/回调代际/取消与真实关闭终止恢复、私有暂存所有权；拒绝未知长度小报造成的静默截断、权限丢失后半成品和旧回调重复移交。只维护独立入口包和probe，不碰正在推进的Apple正式宿主。

读原文档/验收JSON，云端API核实受测source、真实run/作业/工件；比较交回HEAD与tested source差异。沿真实调用流复核输入、输出、错误、取消、提交和释放，不能仅抄上一位agent的总结。

对确认缺陷补最小实现与可执行负例，保留原用例和本包原平台范围。原strict若缺真实job认证、唯一ZIP成员或二进制身份，补齐相应拒绝例。若仅语义或证据缺口，明确限定，不制造功能通过；不能越权改共享模块来让测试通过。

原代码无缺陷且原证据足够时，交一份定向复核结论并保留原受测身份即可。任何源码/测试/工作流修改后，按本包原平台真正执行新source；证据只归该source。完成和交回格式见共同约束。

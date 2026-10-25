# T03：跨操作系统原书与修订往返复审

先读[本批共同约束](README.md)，再读[原J22完整任务](../reader-next-wave/cross-os-relay.md)。本包是交回后的独立复审/必要修复，原任务的完整目标和验收继续有效，不从头重做。

- 固定起点：`9ff063dcc6b898fb0c776edabadf743919045a7d`
- 原交付分支（只读）：`codex/reader-cross-os-relay`
- 新的唯一写入分支：`codex/dot-cross-os-relay-review`
- 允许修改的全部路径：

- `tests/reader_cross_os_relay/**`
- `.github/workflows/reader-cross-os-relay.yml`
- `docs/READER-CROSS-OS-RELAY.md`
- `docs/validation/reader-cross-os-relay.json`

## 本轮必须完成

审计四方向artifact-relayed HTTPS传递是否逐端核原始字节和来源；绑定平台、source/run/attempt、双方原始工件和public SDK回读，拒绝缺包/换源/换attempt/假对端。不要把传输脚本通过扩写成六台设备的产品同步通过。

读原文档/验收JSON，云端API核实受测source、真实run/作业/工件；比较交回HEAD与tested source差异。沿真实调用流复核输入、输出、错误、取消、提交和释放，不能仅抄上一位agent的总结。

对确认缺陷补最小实现与可执行负例，保留原用例和本包原平台范围。原strict若缺真实job认证、唯一ZIP成员或二进制身份，补齐相应拒绝例。若仅语义或证据缺口，明确限定，不制造功能通过；不能越权改共享模块来让测试通过。

原代码无缺陷且原证据足够时，交一份定向复核结论并保留原受测身份即可。任何源码/测试/工作流修改后，按本包原平台真正执行新source；证据只归该source。完成和交回格式见共同约束。

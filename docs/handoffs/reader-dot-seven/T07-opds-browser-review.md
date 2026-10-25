# T07：OPDS 浏览与获取适配复审

先读[本批共同约束](README.md)，再读[原J02完整任务](../reader-next-wave/opds-browser.md)。本包是交回后的独立复审/必要修复，原任务的完整目标和验收继续有效，不从头重做。

- 固定起点：`3ca9d9fed564dbcba11fc95a034244c5cfe8c762`
- 原交付分支（只读）：`codex/reader-opds-browser`
- 新的唯一写入分支：`codex/dot-opds-browser-review`
- 允许修改的全部路径：

- `apps/reader/opds-browser/**`
- `tests/reader_opds_browser/**`
- `.github/workflows/reader-opds-browser.yml`
- `docs/READER-OPDS-BROWSER.md`
- `docs/validation/reader-opds-browser.json`

## 本轮必须完成

核相对/绝对/百分号资源URL、同源凭据、分页与entry寿命、未知媒体、获取链接选择、重定向和失败清理、取消/重入/所有权。保持复用原OPDS/WebDAV/侧载公开包，不新增解析器或网络后端，不把模块通过当宿主浏览界面通过。

读原文档/验收JSON，云端API核实受测source、真实run/作业/工件；比较交回HEAD与tested source差异。沿真实调用流复核输入、输出、错误、取消、提交和释放，不能仅抄上一位agent的总结。

对确认缺陷补最小实现与可执行负例，保留原用例和本包原平台范围。原strict若缺真实job认证、唯一ZIP成员或二进制身份，补齐相应拒绝例。若仅语义或证据缺口，明确限定，不制造功能通过；不能越权改共享模块来让测试通过。

原代码无缺陷且原证据足够时，交一份定向复核结论并保留原受测身份即可。任何源码/测试/工作流修改后，按本包原平台真正执行新source；证据只归该source。完成和交回格式见共同约束。

# F4：文件夹批量导入

先读[共同约束](README.md)，从固定起点创建`codex/reader-batch-import`。
目标是让用户选择本地文件夹后，按有界队列逐本导入，取消/失败不伤已有书籍。

## 文件归属

仅新增`apps/reader/batch-import/**`、`tests/reader_batch_import/**`、
`.github/workflows/reader-batch-import.yml`、`docs/READER-BATCH-IMPORT.md`、
`docs/validation/reader-batch-import.json`。

## 交付契约

- 可选安装包`EXReaderBatchImport 0.1.0`，公开C ABI`reader_batch_import.h`。
  本地文件夹枚举与SDK导入分成两个可独立调用的阶段；不创建线程或常驻监测。
  枚举可在普通I/O worker，导入必须在借入library的SDK owner上串行执行。
- 首版覆盖现有九格式，扩展名只作候选过滤，最终仍由现有导入接口验证。
  递归需显式配置，固定最大深度、目录/候选数、文件路径长度与待处理内存上限；
  每批1..100，明确续批和错误策略。超限不谎称完整扫描，不无限缓存整棵目录树。
- 不跟随符号链接/目录联接走出用户选定根，不接受非普通文件。
  枚举后文件可能变化：导入时重新打开/校验，失败逐项报告，不信任旧stat。
- 必须调用安装后的`EXReaderSideload`，沿用32MiB重排内存/128MiB流式上限，
  PDF稳定私有文件、协作式取消与created语义。不能复制一套import或查SDK私表去重。
  返回每文件状态、book_id、created和是否已提交；精确重复保留用户元数据。
- 产品目录映射/修订/outbox仍由root处理；结果回调在本次SDK导入结束后调用，
  由宿主走既有映射流程。不能把SDK提交宣称为产品映射也提交，不能偷偷写产品SQL。
- 取消只阻止后续未提交工作；已提交结果必须交回，不删除重复命中的旧书。
  不接入系统选择器、WebDAV账号、宿主UI或新导入协议。

## 云端出口

Windows/Linux/macOS安装后C/C++消费者。云端生成多层目录、Unicode/空格路径、
非书文件、重复文件、损坏文件、链接/联接、枚举后修改或删除、限额与取消。
覆盖九格式真实导入及现有storage mode保持；导入失败、部分成功、重开及重投逐项可辨。
通过公开SDK回读原件证明精确性；原书/旧metadata不得因取消或重复被改掉。
系统选择器及产品UI不在模块验收中。

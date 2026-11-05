# G06：仅移除本机下载与中断恢复

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-local-downloads`。
类型：功能；优先级：P0；分发：Claude Code。

## 文件归属

- `apps/reader/local-downloads/**`
- `tests/reader_local_downloads/**`
- `.github/workflows/reader-local-downloads.yml`
- `docs/READER-LOCAL-DOWNLOADS.md`
- `docs/validation/reader-local-downloads.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

可选 EXReaderLocalDownloads 0.1.0，C ABI。复用 catalog_find/has_local/remove_local、library_source/delete、sideload原件导出/导入，实现只移除本机原件和本机映射，保留全局书目、分类、产品阅读修订和全部远端内容。
“移除下载”绝不能创建远端删除墓碑。SDK和产品库没有跨库事务，使用模块私有durable intent记录明确阶段并幂等恢复；不复制运行中的SQLite文件，不访问SDK私表。
调用者须在SDK owner上释放相关source/readers，并停止触及该原件的网络任务后调用。检查身份及重复本机映射，不能删错另一本书或旧重复。
遗留SDK-only笔记/进度不得随原件静默丢失：保留可恢复数据，或明确拒绝移除并给出可操作状态；不得假设已迁移产品修订。模块不自行设计新同步协议。
重新下载/导入仍沿用原格式+原始SHA身份。取消、异常和重启必须可恢复，不产生用户数据损失。

## 云端出口

Windows/Linux/macOSinstalled消费者；云端-only、本机已下载、重复SDK ID、遗留notes/progress、占用拒绝、每个持久阶段真实kill/reopen、磁盘/映射失败、重复请求及重导入。
独立核对产品metadata/history/outbox和远端对象不变；释放source规则与失败后的可读性明确测试。不能只用异常注入代替真实进程终止。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `apps/reader/store/native/catalog.h`
- `include/exr/library.h`
- `extras/sideload/include/exr_sideload.h`
- `docs/READER-PRODUCT-PLAN.md`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。


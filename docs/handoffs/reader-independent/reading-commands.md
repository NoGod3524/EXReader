# G03：进度、书签、标注的产品具型命令

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-reading-commands`。
类型：功能；优先级：P0；分发：Claude Code。

## 文件归属

- `apps/reader/reading-commands/**`
- `tests/reader_reading_commands/**`
- `.github/workflows/reader-reading-commands.yml`
- `docs/READER-READING-COMMANDS.md`
- `docs/validation/reader-reading-commands.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

可选 EXReaderReadingCommands 0.1.0，C ABI。复用 reader_rs_encode_v2、reader_revision_local_reading、heads/get/selected，提供保存阅读进度、点书签、高亮、批注正文编辑及显式删除/恢复。
输入capture由调用者真实公开SDK捕获；保留 REFLOW_GLOBAL、EPUB_CHAPTER、FIXED_PAGE，重复spine以part+path区分。不要根据整书百分比/页码猜锚点。
完整 observed heads 和固定 revision ID 由调用者传入，陈旧heads拒绝；精确重试不产生第二条历史/outbox。注释编辑保留原selector和未知范围，不伪造重定位。
沿用现有 wire v1/reading anchor v1/v2、墓碑与restore语义，不新增实体，不写SDK notes副本、不自动改变当前页面。所有调用遵循owner和no-reentry，限制输出与错误信息。
缺少公开能力时先交最小复现给root，不能修改reading-state/revisions/commands共享目录。

## 云端出口

Windows/Linux/macOS安装后消费，四格式真实capture、UTF-8边界、重复spine、点/范围、v1兼容、所有heads状态、并发与陈旧提交、墓碑后显式恢复、响应丢失后的同ID重试、提交失败history/outbox不分裂。
每项经公共API独立回读wire/heads/outbox，核对源书、SDK notes和当前进度不变。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `apps/reader/reading-state/include/reader_reading_state.h`
- `apps/reader/revisions/include/reader_projection.h`
- `apps/reader/commands/include/reader_commands.h`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。


# G05：标注 Markdown／JSONL 导出

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-annotation-export`。
类型：功能；优先级：P1；分发：Claude Code。

## 文件归属

- `apps/reader/annotation-export/**`
- `tests/reader_annotation_export/**`
- `.github/workflows/reader-annotation-export.yml`
- `docs/READER-ANNOTATION-EXPORT.md`
- `docs/validation/reader-annotation-export.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

可选 EXReaderAnnotationExport 0.1.0，C ABI，直接使用 annotations_page、heads/get、reader_rs_decode，不依赖G03/G04。
JSONL导出保留实体身份、选择状态及每条原wire的精确字节（用定义明确的字符串转义编码；独立读取须可逐字还原）。Markdown为纯文本分享，保留书名、引用、批注和未定位/冲突状态；不执行HTML或联网。
keyset流式写出，不持有整本书所有标注。冲突的多head逐个保留，墓碑和缺parent状态不得假装唯一当前批注；不提供隐式导入或冲突解决。
临时文件+flush+原子发布；失败/取消保留旧有效导出，路径/输出大小预算明确。只读产品/SDK，不含账号秘密、绝对私有路径或本机SDK行号。

## 云端出口

三桌面installed消费者；中文/emoji/组合字符、换行/引号、Markdown/HTML样本、空导出、千条分页、v1/v2、冲突/墓碑/缺parent、取消和写入失败。
用与实现独立的读取器验证JSONL还原exact wire；核对Markdown可见文本及导出前后数据库/进度未改。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `apps/reader/revisions/include/reader_projection.h`
- `apps/reader/reading-state/include/reader_reading_state.h`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。


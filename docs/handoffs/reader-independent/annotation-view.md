# G04：按书书签与标注列表快照

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-annotation-view`。
类型：功能；优先级：P0；分发：Claude Code。

## 文件归属

- `apps/reader/annotation-view/**`
- `tests/reader_annotation_view/**`
- `.github/workflows/reader-annotation-view.yml`
- `docs/READER-ANNOTATION-VIEW.md`
- `docs/validation/reader-annotation-view.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

可选 EXReaderAnnotationView 0.1.0，C ABI。直接复用 reader_revision_annotations_page 和 reader_rs_decode，不依赖本轮其他新包。
每批1..100，按稳定全局annotation_id keyset翻页，复制借用字符串；列表快照与当前SDK对象的寿命分离。区分书签/范围高亮/批注，并保留SAFE、CONCURRENT、PENDING_PARENTS、BLOCKED_RESTORE、墓碑。
冲突不得自动挑一个head；非SAFE不能伪造正文。未定位/歧义/旧版本照实展示状态，模块不执行导航，不改变页面、进度、history、outbox或SDK笔记。
明确owner、取消、回调重入、页/字符串释放、最大单条及总输出预算。

## 云端出口

三桌面平台installed C/C++；>1000条、100项续页与反向、删除/并发插入、跨书拒绝、v1/v2、重复spine、缺parent/并发/墓碑、取消每轮询点、重入、释放SDK后快照可读。
直接公共revision分页独立建立预期，验证无重复/遗漏及前后产品历史、SDK进度/notes逐字不变。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `apps/reader/revisions/include/reader_projection.h`
- `apps/reader/reading-state/include/reader_reading_state.h`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。


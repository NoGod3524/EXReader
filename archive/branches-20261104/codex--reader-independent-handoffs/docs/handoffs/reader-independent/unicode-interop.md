# G14：Unicode 路径、名称与跨平台产品回归

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-unicode-interop`。
类型：测试；优先级：P1；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_unicode_interop/**`
- `.github/workflows/reader-unicode-interop.yml`
- `docs/READER-UNICODE-INTEROP.md`
- `docs/validation/reader-unicode-interop.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

只新增公开安装后组合消费者，覆盖Unicode路径与书名/作者/子书架/标签/系列在导入、catalog排序查询、commands提交、revision传输/投影、重开中的字节和语义一致。
包含中文、emoji、组合字符NFC/NFD、俄文、阿拉伯/希伯来混排、RTL控制符、长字符串及平台保留字符。遵守现有NFC sort_title与SQLite字节/ASCII大小写契约，不能擅自加Unicode折叠或改用户原字段。
Windows消费者用真实UTF-16→UTF-8入口，避免重演F5测试参数损坏。独立冻结输入/预期，不调用被测逻辑生成预期。
不能把字段存储正确称为排版/读屏正确；不修改SDK或产品schema。

## 云端出口

Windows/Linux/macOS同源实际执行、原件/修订精确SHA、公共API回读、二次重开、跨平台输出比较。拒绝非法UTF-8、截断或预期外规范化。
保存逐例原始结果和消费者身份；真实用户文档及旧1710目标不纳入本包计数。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `apps/reader/store/native/catalog.h`
- `apps/reader/desktop/catalog_sdk.c`
- `apps/reader/revisions/include/reader_projection.h`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。


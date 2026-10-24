# G08：可选模块同前缀安装与组成验证

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-module-composition`。
类型：测试；优先级：P0；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_module_composition/**`
- `.github/workflows/reader-module-composition.yml`
- `docs/READER-MODULE-COMPOSITION.md`
- `docs/validation/reader-module-composition.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

使用固定基线已存在的SDK、catalog/revisions/commands/metadata、WebDAV/session/credentials、reading-state/search/preferences/batch-import/sideload，不依赖G01-G06。
装入同一前缀，在全新目录仅用find_package和安装头/库构建C11与C++消费者；逐包头自包含、导出target、静态依赖、重定位及默认reading构建不带可选模块均有真实检查。
真实导入→search捕获→reading编码→revision→WebDAV→另一SDK resolve，设置/批量导入共存，最终链接图只能有一份产品SQLite provider。
不增加元框架或统一超级构建层，只交组成测试和失败定位。

## 云端出口

Windows/Linux/macOS实际执行；Android/iOS可附交叉编译或设备执行，逐项分别授予。精确记录实际消费者、安装文件和依赖SHA。
破坏target/漏依赖/重复SQLite/源码include泄漏等负例应导致门禁拒绝；不能用成功configure冒充运行。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `tests/reader_reading_v2`
- `apps/reader/session/CMakeLists.txt`
- `cmake/EXReaderConfig.cmake.in`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。


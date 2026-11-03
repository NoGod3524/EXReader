# Apple CI 首次运行复核

SDK 核心契约候选 `40ac811b0a872587641e01ff0cfc33a376e93abc`，父提交 `95100501eeef9c6325be8b3882aa400c99cf000f`。
运行 [41705105811](https://github.com/NoGod3524/EXReader/actions/runs/41705105811)，attempt 1，job `126158207426`，macos-14，结论 failure。
首次失败分类：**构建配置失败，非行为失败**；不计入共享 provider 验收。
本次使用已批准的一次、单作业、20 分钟额度；没有重跑。来源见 `source.json`、`run.json`。

## 四项证据状态

| 要求 | 本次实际结果 |
|---|---|
| 全部应用受控映像仅一份 SQLite 实现 | 未闭合。下载工件中的 provider 有 278 个 sqlite3_ 定义、SDK 定义 0 / 引用 38；消费者尚未构建。原始输出和二进制 hash 在 `partial-symbols.json`、`*-nm.stdout.txt`。 |
| FTS5 测试名与数量 | `sqlite-provider-check` 1/1 passed，见原始 `fts5-provider.xml`；`shared-sqlite-sdk-product` 未执行，不能计作通过。 |
| stage 下 sqlite 文件扫描 | `stage-sqlite-scan-from-artifact.json` 列出下载的部分 stage 中 13 个条目及 hash；SDK 已安装、ProductCatalog 尚未安装。远端原定的 find 步骤未到达；此复核扫描不能冒充完整远端 stage 扫描。 |
| 故意内嵌 SQLite 的 Apple 负例必须报错 | 未执行；在前序构建失败后跳过，不计通过。 |

原产品测试 `product-originals`、`native-product-catalog` 均未执行。

**两项仍待 CI**

## 失败原因及本地修复

`reader-original-import-check` 编译 `tests/reader_catalog/original_import_check.cpp` 时，AppleClang 对 `nullptr` 与花括号初始化报语法错误。
`reader_original_import` 声明的 `cxx_std_17` 为 PRIVATE，没有传到测试目标；原始 `95100501` 中同样缺少该目标的标准声明。
这是本次构建中实证出现的编译阻塞，尚未发现共享 provider 的运行时回归，不归为 F07 产品回归。

修复只给 `reader-original-import-check` 增加 `target_compile_features(... PRIVATE cxx_std_17)`，不修改测试源码或断言。
本地同一测试源码以 C++98 编译失败、C++17 编译通过；随后显式设置目录默认 C++98，CMake 为该目标生成 `-std=gnu++17` 并构建成功。
原始输出：`compile-c++98.log`、`compile-c++17.log`、`fix-configure.log`、`fix-build.log`。
本地编译通过不等于 Apple 验收通过。

`source-fix.patch` 包含该一行修复及下一候选的固定父提交准入调整。
后续候选仍以 `95100501` 为 SDK 内容基准，准入要求父提交精确为已运行的 `40ac811b`，继续检查同一独占路径及 catalog/src/include/bindings/version 不变。
该修复此时未提交、未推送；后续已获有条件授权，前置核对见 `../limited-build-preflight/review.md`，下一运行只记为“限时构建验证”。

## 原始工件与完整性

工件 `13265761623`，8,820,905 bytes，SHA-256 `cf7318c9f0ffed79511867548de8123bb0388cdcc0a59722b2b3090516700ada`。
下载 ZIP 的实际 SHA-256 与 GitHub metadata 及上传日志一致；原始 ZIP 保留在候选工作树 `build/sdk-ci-41705105811.zip`。
`artifacts.json` 保存来源元数据，`job.log` 保存连接器返回的完整解码日志；顶层 `artifact-sha256.json` 记录本目录文件 hash。
ZIP 上传时符号链接可能展开为副本，三个 provider dylib 名称内容 hash 相同，不能仅按文件名数量推断三份运行时实现。

catalog 未修改。当前结论为验收未完成。

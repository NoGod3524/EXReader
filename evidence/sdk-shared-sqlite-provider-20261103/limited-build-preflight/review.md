# 限时构建验证：前置条件

## C++ 标准定性

本次新增 C++17 声明**仅测试目标需要，不改变 SDK 消费者要求**。
失败源码为 `reader-original-import-check` 的测试实现，使用 `nullptr`、花括号初始化；该目标原来没有编译标准声明。
ProductCatalog 的 C++ 实现目标 `reader_original_import` 已有 PRIVATE C++17 声明，该实现要求不传播到安装后的接口。
SDK 核心为 C11。安装的 SDK、ProductCatalog、original_import、SQLite 头均提供 C 接口，C++ 下使用 `extern "C"`，未新增 C++17 类型或语法，也未向导出目标添加 C++17 usage requirement。

`consumer-CMakeLists.txt` / `consumer-cxx98.cpp` 是 install-then-consume 核对用例：只从安装前缀 find_package，并链接 SDK、ProductCatalog 的 original_import 与公开 provider。
本地以明确的 `-std=c++98` 编译、链接、执行成功，四个导出目标均未带 `cxx_std_17` 接口要求。
输出保存在 `consumer-configure.log`、`consumer-build.log`、`consumer-run.log`。
现有 C 联合消费者保留。无需把“C++ 消费者需 C++17”写入 NATIVE_API.md / README，也无需新增 C++17 接入契约。

## 改动清单与 R 候选

逐文件完整清单在 `changed-files.json`，同时标注整个 SDK 重放候选相对 `95100501` 的文件、以及本次相对 `40ac811b` 的后续变更。
受保护路径逐项标记如下，均**进入 R 候选**：

| 路径 | 处置 |
|---|---|
| `CMakeLists.txt` | 进入 R 候选；前一 SDK 重放提交已修改，本次不再改动 |
| `cmake/deps.cmake` | 进入 R 候选；前一 SDK 重放提交已修改，本次不再改动 |
| `cmake/install_dependencies.cmake` | 进入 R 候选；前一 SDK 重放提交已修改，本次不再改动 |
| `cmake/EXReaderConfig.cmake.in` | 进入 R 候选；前一 SDK 重放提交已修改，本次不再改动 |

`src/`、`include/`、`tests/fixtures/`、`bindings/`、`native.yml`、`reliability.yml` 未修改。
本次源码增量是 `apps/reader/store/native/CMakeLists.txt` 的一行测试标准声明，及专属 workflow 的固定父提交准入、验证类别；其余增量均为 evidence。
不改 catalog、测试断言、SDK 版本或默认分支。

## 运行分类与终止规则

首次 run `41705105811`：**构建配置失败，非行为失败**，不计入共享 provider 验收。
后续这一次运行：**限时构建验证**，macos-14 单作业、上限 20 分钟、不自动重试。
绿色只关闭本构建项，保留 run id、原始产物与实际检查结果，不写成 Apple 验收通过。
红色记录首条 error 并转已知问题，不再申请第二轮。

保留原状态原文：**两项仍待 CI**。它指首次运行未执行的 `product-originals`、`native-product-catalog`；后续真实执行结果另记，不覆盖历史。

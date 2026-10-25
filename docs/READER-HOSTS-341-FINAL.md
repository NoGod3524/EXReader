# 原生宿主 3.41 共同候选

独立分支 `codex/reader-hosts-341-final`。原 3.40 冻结 SDK、原失败运行、预算和证据保留。
共同产品验收尚未通过，不能从单包或单向互通结果转授。

## 已合入的来源

- 共同 3.40 主线 `07ebe8786434ef384c97ccdb451242d3c6aee6cb`。
- GTK theme、实际旧/新记录兼容与导航 draw 观察/等待的普通合并点
  `58eda15d886268e054f2211a837b4032e946e165`；其最终同源码运行仍在进行。
- Android 已封存主题 `1b3cfd1413fa5ebade31be6958f835f6de3b5290`。
- 已封存 parser 拼写策略与 Apple 原生兼容控制 `e8ed25c1cd7ccb33405611e27f9ad47fba8c9e34`。
- Apple 已封存 startup/shelf publication 修复 `897f8973c1a8c74fa5aaf9a470d02e6914faeded`。

普通合并后的生产基础 `2dae171b75f04484813cd03487bbb9b5aab81c71`。
SDK 保护树精确为独立候选 `edddc463c06ed5731195cdb8f06b2df6dff7699e`；
本分支不采用选择器 v3，不改产品 schema1。Windows F3 完整交付与原子提交取消修复尚待合入。

## 后续四模块的实际 SDK 依赖缺口

此前版本支持包早于 cloud-import、thumbnails、book-information、local-downloads。
这四包仍在构建和安装配置中写死 SDK 3.40，不能直接用于实际 3.41 的共同安装前缀。
现在与早期模块一样显式选择 `EXR_SDK_VERSION`，只接受精确 3.40.0 或 3.41.0，
默认仍为 3.40.0。安装配置固定实际构建版本，不能在使用时悄悄换 SDK。
模块 C ABI、实现、schema 和旧 wire 未改。

`reader-later-module-sdk.yml` 在 Windows、Linux、macOS 分别构建真实旧/新 SDK，
分别安装四模块及公开依赖，编译并运行安装后的 C 消费者，并测试错误版本、
错误 SDK 请求和两个方向的混用拒绝。此门禁只证明依赖安装/链接与拒绝行为，
不能代替完整 27 包组合、原功能测试、原生 UI 或六平台互通门禁。

受测源码 `49b2a7c86173181f8f79a760315ddb8ca2312bd1`，
[40185877681](https://github.com/NoGod3524/EXReader/actions/runs/40185877681) attempt1，
Windows/Linux/macOS 三个 producer 全部 success，各 16/16。只授予上述安装/链接/拒绝范围。
本轮没有独立 ZIP 汇总作业；以下为 Actions API 声明的工件信息，本地未下载或解析工件。

| 平台 | 工件 ID | 字节 | 声明 SHA-256 |
| --- | ---: | ---: | --- |
| Linux | 12595393891 | 8,370,259 | `c8661ea83579ac9e81248d0aaa27a323f744c91bfa1a2f1dcb9eda41b0cbd9bb` |
| macOS | 12595499367 | 7,111,243 | `a4665a6e5de3422f57bad28febe0d75703a1ab1ec34e5148bd12d83b2f20e63e` |
| Windows | 12596053321 | 4,672,055 | `02c872fdc0b14706bc6fde124a51664be406c37ade9456282b4b3bd51247dfcc` |

有效期均为 `2027-01-23T10:42:28Z`。

## 完整组合的显式 3.41 配置

独立准备分支 `codex/reader-composition-341` 保持上面的生产代码不变。
配置提交 `f9671923a854901d19bddd0396073dbc90fab222` 只为八个安装后消费者增加
默认 3.40 的显式版本参数，并在三个原配置调用点传递该参数。
原消费者、夹具、功能判断、配额、单提供者检查和全部失败断言不改。

G1 原本会另编译 `7817caa9…` 的旧本地下载实现作为回归负对照。
在显式 3.41 模式下，只把它归档副本的两个 CMake SDK 依赖声明改为实际请求版本，
源码实现逐字不改；原/新两个配置文件都保留在各阶段证据中。
默认 3.40 路径不做这项替换。不能把改过构建配置的副本称为完全未改的旧包。

新工作流的 compose/aggregate 两 job 从原共同运行 `07ebe878…` 逐字保留，
只允许源 guard 入口、显式 SDK 配置参数和严格汇总调用身份这三类适配。
Actions 先比对整段原 job，随后在三平台运行完整原测试、前缀迁移和 41 个严格协议负例。
该完整运行尚未通过，不能从前面的四模块结果转授。

## 共同源码仍需完成

原完整组合需以显式 3.41 前缀重跑，保留原 C/C++ 消费者、搬迁前缀、单 SQLite/SDK
提供者、全部原 G1 判据和负例。宿主需要同源码的完整 Windows F3 与既有套件、GTK41
设置及原导航/记录/导入/账户/集合/无障碍、Android130、Apple七组与实际记录方向验证。
旧 Apple NUL 发送失败保持；已封存 Android→Apple 仅原生单向范围，双向仍 pending。

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
不能代替完整 27 包组合、原功能测试、原生 UI 或六平台互通门禁。当前尚无通过结果。

## 共同源码仍需完成

原完整组合需以显式 3.41 前缀重跑，保留原 C/C++ 消费者、搬迁前缀、单 SQLite/SDK
提供者、全部原 G1 判据和负例。宿主需要同源码的完整 Windows F3 与既有套件、GTK41
设置及原导航/记录/导入/账户/集合/无障碍、Android130、Apple七组与实际记录方向验证。
旧 Apple NUL 发送失败保持；已封存 Android→Apple 仅原生单向范围，双向仍 pending。

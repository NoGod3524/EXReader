# D18：移动端真实动作与独立存储观察

固定 seed：`d263ce5228838ac90c0a0dc13a5193d4a7739681`，不是已验收生产 BASE。
本包只新增专属测试、workflow、证据文档；不改 Apple owner、D11 旧结果、SDK、schema、预算或旧 guard。

## 观察边界

- iPhone/iPad 从同一当前 Actions SHA 新构建真实 SwiftUI APP 和产品库。SDK 为冻结 `edddc463c06ed5731195cdb8f06b2df6dff7699e`，认证既有 producer `72c6bbdd14ebf3be453fa7f0da81119d52675eb5`、run `40203714083/1` 的原 macOS/iphonesimulator ZIP。其旧产品库重新用本轮源码构建；不得将旧产品结果拼入本轮。
- 原 D11 17 命名语义项保持，额外增加真实 Files picker 选择损坏 EPUB。原 import 项仍为 D11 的真实 fixture-native 入口；取消通过实际 Files picker。settings 只指 page theme，resume 只指 reopen。
- 独立 macOS observer 通过 `simctl get_app_container` 定位真实 app data，再唯一识别 `Library/Application Support/EXReader/**/library.sqlite` 及同目录 `reader-catalog.db`；缺失/歧义必须失败。不是 *.sqlite 模糊枚举，更不是 mtime。
- 仅对 live 库打开只读 SQLite 连接备份，不读取 SDK 私有表。副本上的 SDK 数据通过既有 public snapshot routine 的公开 SDK API 读取，包含元数据、progress、notes 和原件数据 SHA。产品副本使用只读 SELECT 完整表内容。
- 每个动作前后均有两次间隔至少 0.5 秒的一致独立读回。正常开书后建立 `opened.idle` 基线，再取消/拒绝；开书、next/previous 等合法进度变化单列，不算失败动作写入。cancel/badfile/disabled-noop 必须完整 SDK/catalog 语义不变；所有动作的原件、revision/outbox 相对打开后基线不变。
- XCUITest、每个动作 AX tree/截图、实际 app tar、真实程序 hash/mode、原始 snapshot 副本和结构化数据、测试日志全部在同轮产物。独立 verifier 在 Actions 内下载并验证原 ZIP 大小/SHA/有效期、同 run/attempt job 结果，绑定所有原始文件；不在本地下载或解析工件。

## 不授予的范围

真机、外接键盘、读屏、modal keyboard focus、完整产品和未运行项均不授予。D11 三轮失败保持原封不动；本包最多三完整 CI 轮（rerun 同样占一轮）。本地仅源码、文档、Git。

入口：`.github/workflows/reader-wave3-d18.yml`。详细每轮结果与最终 handoff 在终态后独立 `[skip ci]` 文档提交封存。

# D16：Apple 大字体原生驱动修复

初始 HEAD / fixed seed：`d263ce5228838ac90c0a0dc13a5193d4a7739681`。任务书：`f8808893f8deafaaeed042ec58ad64a9acc56465` 的 `docs/handoffs/reader-wave3/{README,D16}.md`。

本包只新增 D16 命名空间，未重置工作树，未改产品 owner、原测试、原 guard、SDK 或共享文件。SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e` 与新宿主候选分开；seed 不是已验收生产 BASE。

## 唯一动作投影

原 D10 文档 HEAD：`7e4fcac25120199dd4818a86039e2257f28132a1`；受测 harness `d2e1b55c9cd4ded4201cbb4d1351bc490ef644df`，run `40229896420` / attempt `1`。两次 iPhone 大字体 reader journey 在字体减小控件离开滚动视口后查询 `isHittable` 失败；Mac 6/6、iPad 10/10、iPhone 8/10 原结果保留，绝不算新 source 通过。

`projection.py` 只替换 `DefaultUITests.tap` 内的 12 次全幅 swipe 驱动：每次取当前原生滚动视口与控件 frame，采用视口内有界、低速、停止后抬起的原生拖动；最终在调用 `isHittable` 之前增加完整几何可见性断言。不得用隐藏坐标点击，不降字体，不删任何原断言，不重试点击。原测试类其他内容、原 regression、原 recorder、原 observation contract 保持字节一致，由 Actions guard 验证。

三目标都 checkout 本次真实 `github.sha`；无旧平台 source 拼接。原 Mac 6 条、iPhone/iPad 各 10 条完整 XCTest；手机/平板 medium 与 accessibility-extra-extra-extra-large 各 light/dark。保持原单例 420/900 秒、90 分钟 job 与滚动 12 次上限。仅 Actions 构建、语法、夹具、测试、截图和 ZIP 下载/解析；本地仅源码/文档/Git。

## 证据与保留缺口

复用 D10 collector/verifier 及现有 overlap judge；独立 prior job 重验原 D10 ZIP、程序身份和原失败，不给新运行授予覆盖。每组 XCTest 同时通过原生 `ps`（必要时 `lsof`）观察真实 PID 和可执行文件 SHA，与实际 app 比对。新 verifier 从同 run/attempt 的原 ZIP 重验字节大小、SHA、有效期、manifest、程序/plist、实际 job 与完整命名测试；CI 中原始截图、AX 树、xcresult 保留。

`audit_completed` 仅表示限定 journey 全套通过；不等于全产品、完整 AX/VoiceOver、物理设备、签名、文字裁剪或 macOS 系统大字体通过。Menu wrapper 原始 `isHittable=false` 不被坐标触发成功改写。

轮次最多 3（attempt 重跑也算）。结果待当前功能提交的 Actions；最终证据文档使用独立 `[skip ci]` 提交。

## 最终状态（2026-10-26）

首轮 `40275499967/1` 已 success，受测 `8104bcd872c49da2c683fb482b8c67e958aa4747`。Mac6/6、iPhone10/10、iPad10/10，PNG64/148/134，原ZIP/实际程序/PID同源验证通过；47项负例拒绝。完整中文结果和接入命令在根 `HANDOFF-RESULT-D16.md`。本次仅文档 `[skip ci]` 封存，不改变已受测源码、不启动第二轮。

# 实际 Apple 阅读记录互通出口

固定起点 `b1a7b7891cd394671842164a07a86c8e316dace3`。全部生产 owner、SDK、
模块、wire 与原兼容测试保持该提交的原样内容。本分支只增加测试、独立工作流与本文。

实际 `HostSession` 导入 TXT、有界 EPUB、PDF、CBZ，使用实际捕获与
`HostReadingWorker.submit` 生成每格式进度和书签，另对前三格式生成真实范围高亮。
从公开 outbox 导出原始完整 wire、book 修订及全部祖先，通过已有公开 SDK 流式出口
导出原件。manifest schema1 的 originals/revisions/reading_records 与 Android 对接约定一致。

Apple 的 sender 声明真实裸版本 `3.41.0`，不替换成 Android 前缀。
实际 executable、唯一 dyld SDK DSO、原始 wire 和原件均保留并散列绑定。
新的接收进程用公开 receive 存入原字节，完整唯一 reading graph 接纳后调用实际宿主
位置解析与重新捕获，检查 SDK 状态与产品 outbox 不变；第三进程重开后再解析同一 bundle。
每次运行同时保留原 18 个兼容进程阶段、两 SDK 各 19 项原 owner 测试及 Java20 策略检查。

当前验收：待首次 Actions。首轮目标为实际 Apple sender 与本机独立进程回读；
**实际 Android 双向互通仍 pending**。Android 实际 sender 工件到达后再绑定其原始字节
交给 Apple receiver，并将本分支实际 sender bundle 交回 Android。
本包不授予宿主 UI、真机、六平台同步或完整产品验收。

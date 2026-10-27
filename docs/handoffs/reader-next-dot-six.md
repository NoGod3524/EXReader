# EXReader：六个独立 Dot 工作包

六包分别在 Dot 原生云端独立工作区执行，不使用本机或云端 Codex，不使用电脑操作接口，不再派子代理。固定代码起点为 NoGod3524/EXReader 提交 `b723a9a3a20af7b31729fa1a47b695b20a0c4b8f`；先核对该源码与当前已有验证，避免重复。每包创建自己的 `codex/` 分支，下面指定的新增路径为独占写入范围。不要修改其他平台宿主、共享 SDK、共同工作树或其他包路径；发现必须改共享代码时提交具体修复建议与证据交主协调者，勿自行跨范围修改。

工作区只用于源码、文档和 Git；所有构建、测试、语法检查、夹具生成、性能测量、截图及工件下载解析都只在 GitHub Actions。功能分支 push 和 Actions 已授权；不得修改默认分支、创建 PR、tag 或 Release。保留失败，不能降低冻结 SDK 预算或拼接不同源码/运行证据。交回完整源码 SHA、Actions run/attempt、原始工件身份、实际检查范围、失败及未覆盖项；各包通过不代表完整产品通过。无法使用 Dot 原生源码与 Git 能力时直接报告，勿改用 Codex。

## D21：真实 WebDAV 服务上的桌面原件闭环

分支 `codex/dot-d21-real-service`；独占 `tests/dot_d21_real_service/`、`.github/workflows/dot-d21-real-service.yml`、`docs/dot-d21-real-service.md`。先检查 `tests/reader_webdav_interop` 和 Windows/GTK 实际宿主接力现有覆盖。复用 Apache 和 Nextcloud 容器、已有已安装组件及真实宿主，补齐从一端实际上传原件到另一端下载、导入、打开与 SDK 逐字节回读的可执行缺口。记录服务版本、两个程序和源码身份、原件摘要，覆盖重试与取消后续传或明确不能触发的环节。不得用协议消费者冒充实际宿主，也不声称所有云服务通过；若宿主尚缺接口，以可复现的接口缺口和真实失败结束。

## D22：产品库升级与旧库兼容

分支 `codex/dot-d22-upgrade`；独占 `tests/dot_d22_upgrade/`、`.github/workflows/dot-d22-upgrade.yml`、`docs/dot-d22-upgrade.md`。先检查 `tests/migration`、产品目录版本与现有恢复测试；用真实历史版本产生的产品库或有来源可复现的旧格式数据，验证现有安装组件打开、升级、重开，以及书籍、组织、进度与标注的保留。对未知未来版本、取消或中断失败验证原库可恢复，不把 SDK 私有 schema 当作产品库。数据和每一步来源必须可追溯；任何实际不兼容保留失败并交回。

## D23：跨端真实标注与锚点往返

分支 `codex/dot-d23-annotation`；独占 `tests/dot_d23_annotation/`、`.github/workflows/dot-d23-annotation.yml`、`docs/dot-d23-annotation.md`。先检查 `tests/reader_android_record_interop`、`tests/reader_gtk_record_compatibility` 和 Apple `record_compatibility` 的既有结果；针对仍缺的跨端环节，使用各端已公开的捕获、编码和解析接口，在 Actions 支持的真实宿主或模拟器之间传递同一本原件的进度、书签和标注，核对恢复的位置与原文，不以模拟结果代替宿主操作。明确区分 found、歧义、缺失与失败；不修改冻结 SDK，不把接口互操作称为完整 UI 同步。

## D24：GTK 大书库与长文阅读性能测量

分支 `codex/dot-d24-gtk-perf`；独占 `tests/dot_d24_gtk_perf/`、`.github/workflows/dot-d24-gtk-perf.yml`、`docs/dot-d24-gtk-perf.md`。先检查 `tests/reader_perf_gtk` 和现有 2202 本书真实宿主基线，复用其构造与程序身份验证。补充同一实际 GTK 产品的书架分页、打开长文、翻页和搜索过程的可交互时间、帧时间及内存原始观测，并记录 runner、样本、操作和程序摘要；保留测量失败。不得新增或放宽 SDK 冻结预算，若产品阈值未授权只报告观测，不声明性能达标。

## D25：Windows 与 GTK 键盘可达性

分支 `codex/dot-d25-keyboard`；独占 `tests/dot_d25_keyboard/`、`.github/workflows/dot-d25-keyboard.yml`、`docs/dot-d25-keyboard.md`。先审查现有原生 UI 与可访问性检查，补充两个实际打包宿主可重复的键盘路径：书架、导入、打开阅读、搜索、设置与返回，核对焦点位置、名称及实际动作结果。系统交互或云端能力不足时记录真实阻塞；截图、UI 树和报告绑定同一次源码与程序。键盘通过不等于屏幕阅读器或六平台通过。

## D26：六目标交付依赖与安装说明

分支 `codex/dot-d26-delivery`；独占 `tests/dot_d26_delivery/`、`.github/workflows/dot-d26-delivery.yml`、`docs/dot-d26-delivery.md`。先复用现有六端打包、解压启动与许可核对入口；为能在 Actions 构建的每个目标产出机器可核查的程序/依赖清单、许可来源、安装与首次导入/同步说明，核对真实包身份及缺失依赖。云端不可安装或运行的目标单列未验证，不把旧源码产物拼成同源六包。禁止创建正式发布版本。

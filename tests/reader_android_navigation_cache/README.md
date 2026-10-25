# Navigation query-cache adapter（待公共同源运行）

依据诊断 `40233907741/1` 和云端工件认证 `40234679542`：同一 window/title 下缓存曾返回零行，clearCache 后出现真实行。该差分在第三项 First & chapter 查询，不直接归因先前第四项 Group 失败。

仅生成固定原 `NavigationUiTest.java` 的投影：在两处 active-root、getWindows 及 window-root 查询前调用公开 `UiAutomation.clearCache()`，并在原报告追加投影标识与调用/成功计数。全部原断言、点击、滚动、查询谓词、30 秒等待、原 runner 的 900 秒阶段上限和 18 项名单保持；不设置 ListView、不回顶、不写 owner 数据。原 test、runner、MainActivity、NavigationPanel 的固定 Git blob 均核验，逆投影必须逐字还原原 Java。

编译只在导航 APK 这一次 Gradle invocation 通过 init.gradle 选择生成源码。实际 javac 输入、生成源码哈希、原片段/新片段、test/host APK SHA-256 与证书均保存。原 runner 完整执行后，额外只读检查实际安装的 instrumentation APK 字节，并验证两个阶段实际报告的投影标识与成功刷新计数。旧 strict 原样先执行；新增 strict 认证同 run/attempt 的原始工件 ZIP，再核对编译、安装、报告链。

需 root 在共同 EXTENSIONS 登记的新增精确路径：

- `tests/reader_android_navigation_cache/adapter.py`
- `tests/reader_android_navigation_cache/init.gradle`
- `tests/reader_android_navigation_cache/README.md`

共同 workflow 改动仅五处：prepare；仅导航 Gradle 增加 init 参数；复制导航 APK 后 build 记录；原导航 runner 后 runtime 认证；旧 common strict 后额外 strict。common projection 对这五处做精确逆投影，旧 workflow 其他行仍须逐字一致。

当前只有候选源码，没有构建或运行记录。本分支不启动模拟器或公共整链；由 root 合入 Windows owner 与精确路径策略后统一一个 source 再验收。

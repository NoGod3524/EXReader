# Android 产品库 native owner 接入

[草稿 PR22](https://github.com/NoGod3524/EXReader/pull/22) 只接入现有书架的数据通路和共享 typed 命令，分类界面留在后续阶段。
分支为 `codex/reader-android-collections`，从 Android 书架文档点 `e4600abd` 出发，正常合入共享 commands `d064b5bc`、GTK query `78774a61` 和 local query `3be2473e`。
PR17 与 PR20 的受测分支保持不变。

产品库 `reader-catalog.db` 的生产代码全部通过 `libexreader_product.so`：

| 路径 | 实现与事务 |
| --- | --- |
| 查询、分页、本机映射 attach/remove | 已安装的 `reader_catalog` |
| book、shelf/tag/series、membership 命令 | 已安装的 `reader_commands` → `reader_revisions` |
| metadata/history/outbox 三写 | 仅 `local_project` 内部的一次产品库事务 |
| 原件、阅读、标注 | 原来的公开 SDK；独立 EXRC 数据库 |

一个 native owner 在创建它的宿主 worker 上串行操作 catalog/revision 两个句柄。Java facade 和 native registry 都拒绝错误线程、关闭后的句柄；生产 Java 不再打开系统 `SQLiteDatabase`。
两个产品句柄之间、产品库与 SDK 库之间均没有联合事务。

产品模块交叉编译后独立安装，再由 JNI 查找安装包。它链接单份产品 SQLite 3.54.0，隐藏静态库符号并绑定本库引用。
验收同时保留实际设备上的版本、source ID、compile options、严格 JSON 调用、`sqlite3_open_v2` 所属动态库，以及 Debug/Release 的未剥离符号、链接 map 和动态依赖。
Release 不编译 instrumentation SQL、authorizer 故障与 kill 函数。

共享查询复用同一 keyset 实现。Android 的窄扩展保留 NFC sort title、NFC/NFD author 字面搜索、正反向游标和恢复时的 inclusive 语义。
查询先限定本机映射，再应用 50 行限制；现有 UI 缓存仍为 150 行。稳定 key、SDK ID、精确 title 和当前 metadata 都使用有界的 typed 查询。

JNI 输入经过已验收的 counted UTF-16 → strict UTF-8 转换。emoji 和组合字符保持原文本，孤立 surrogate 与 NUL 在写入前被拒绝。
宿主必须先取得并持久化稳定 revision/entity IDs，再提交创建请求。`prepareCreate` 使用 native OS 随机 ID 和同步持久化；丢失回复时，以相同 IDs、字段及 observed heads 重试。
Android API26 使用 Bionic 的系统随机函数，保留共享模块的 UUID v4 位与 32 位小写 hex 格式。

membership 缺少 retained book history 时返回 `NEEDS_BOOK_BOOTSTRAP`，不写 join/history/outbox。
`BookStore.bootstrapBook` 从公开 SDK 原件分块回读格式、SHA 和长度，再使用当前产品 title、author、favorite、sort title 形成 book 命令。
已有用户 title 不被 SDK title 覆盖；已有 soft delete 要求显式 restore。
book 命令提交后若本机 map attach 失败，保留 SDK 原件和已提交的产品 history，稍后修复映射。

本阶段固定 17 项设备出口，加两个真实进程中断边界。原 112 项为 12 shelf catalog + 10 UI + 8 catalog + 14 mapping + 2 recovery + 66 host；原证据门禁仍为 48 + 20 + 19 = 87。
旧 catalog/mapping/shelf 夹具改用同一个产品 provider 的 Debug 工具。迁移出口单独由旧系统 provider 建立 schema1 文件并完全关闭它，再交给 native owner；两个 provider 从不重叠操作该文件。
中断前的 SQL 函数在当前事务里记录 history/outbox/tag 数量 `1,1,0`，随后真实 kill；提交后边界记录 `1,1,1`。恢复检查实际数据和稳定请求重试。

Gradle connected 测试结束后会卸载目标应用。流程保留这 17 项 XML，再重装同 hash APK，手动运行同一组 17 项并明确传入 source/run/attempt，然后采集原始 instrumentation 与产品 provider 报告。
四个 kill/recover 阶段沿用重装后的同一应用。校验器检查精确具名通过、APK hash、产品库 build ID 和保留文件路径，拒绝把 `run-as` 错误当作 JSON 报告。

本地工作仅源码、文档与 Git；构建、语法、夹具、设备执行及证据检查均在 Actions。SDK 八保护树固定为 `9854061be331fe603a1822d9b2b36ee357154927`，产品 schema1 与既有预算不变。

受测源码为 `8f7c011aafd4d7f900ef42106fa41e2150a66d58`，
[专项运行 40049878764](https://github.com/NoGod3524/EXReader/actions/runs/40049878764) attempt 1 已严格通过。
17 项 Gradle XML、同 hash APK 手动 17 项、2 个中断恢复、原 112 项功能与 87 项门禁都来自这一轮；新增的证据拒绝检查为 19/19。

同源码 [commands 40049880444](https://github.com/NoGod3524/EXReader/actions/runs/40049880444) 两端通过 77/76 + 59 + 33 + 32 + 33；
[共享查询 40049881933](https://github.com/NoGod3524/EXReader/actions/runs/40049881933) 三端各通过原 12 组及查询 10 组。
完整身份、APK/原生证明摘要、工件 digest 和未授予通过的历史失败见 [验收记录](validation/reader-owner-android.json)。
此前 `e036aa78` 的 17 项和中断原件真实通过，但报告在应用卸载后采集失败；该轮保留为拒绝记录，未拼入最终验收。

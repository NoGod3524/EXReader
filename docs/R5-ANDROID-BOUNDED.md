# H10 Android bounded 候选

当前 SDK 守卫及 Android 差异起点为集成人正式冻结的 `9c69bc4c7efb0cff68ced27562709fe597189041`。
最终声明等待 Apple/Android 合入后的共同源码 S；同 S 的 Android 整轮用作本包最终验收。

候选起点 `fd210224a4eba206762c08de435a5e9edfdf2a90`，SDK schema 7 API 已稳定。
接续合入 SDK 包 `ce5d664c9f76d0613df6d79b27568a7039c4a81e`；集成人授予该源码为正式 K_reading 后，
正式 `SDK_BASE` 与 Android 差异起点 `REVIEW_BASE` 均固定到它，ownership 覆盖本次完整受测源码。
本分支实现 app-local JNI／Java，不修改 SDK 与共享 JNI。所有构建、测试、夹具、散列和证据处理在 Actions。

新导入 EPUB 走 package-only file import；去重后查询 storage mode。
bounded 书从同一书库 owner 的 `exr_library_source` 打开 publication/chapter pager，选文和 virtual nodes 只持有当前页文字窗口。
进度采用 part/path/章内 selector；恢复先 resolve，不精确时明确显示 stored-offset fallback 并保留原记录。
新 notes 使用独立 EPUB API，评论修改不重抓选区，导航只接受 FOUND。legacy EPUB／其他重排与 PDF/CBZ 保留原入口。

候选工作流 `r5-android-bounded-candidate.yml` 首轮源码 `50af703c38dd192533a8672ea79fa31315572459`，
run `39864510415` 的 SDK／三 APK 云端构建通过；该首轮没有运行模拟器。
接续候选增加原 45+10 和独立 bounded 8、原 48 与额外 16 项门禁，固定 `candidate_only=true, accepted=false`。
`ANDROID_CANDIDATE_SDK_BASE` 只用于旧候选工作流；正式 `wp13-android.yml` 不设置候选开关，
必须原 45、review 10、新 bounded 11（原 8 加 3 项错误边界）、原 48 与额外 16 门禁同次通过后才允许 `accepted=true`。
原 45+10 IDs、49 页／49 actual next／0 recovery、48 门禁不删减；真实 next 在 C 调用点计数，
seek／恢复扫描不栅格化前页；新增专项及模拟器闭环仍须完整执行。

范围仍为 API 34 x86_64 模拟器，`physical_device_execution=false`；真机／签名／TalkBack 单独验收。

## 保留的首个完整运行

源码 `a01259117c2600c6805abf36c33bcef892dc87d8`，run `39865644335` 未通过；云端诊断
`39867475035` 只读取原 run 的材料，不授予验收。原 walkthrough 44/45：`cancel_large_import`
在快速 package-only 导入后未观察到 Cancel；原 review 9/10：`destroyed_activity_releases_worker`
的新 owner 未在原 20 秒观察窗进入 page-49 progress attempt；新增 bounded 8/8。
原 48 与额外 16 门禁因 preflight 拒绝而未通过，不拼接旧结果。
接续诊断 `39868075239` 从该 run 原件确认真实顺序计量为 49 页／49 native next／0 recovery，47868 ms。

接续让取消用例使用真实复制后的既有 debug gate；恢复复用 resolve 的同一 pager，避免重复章节建索引，
并记录 open/scan 耗时。跨 owner 提交造成的 pending source 失效会重开、解析、重绘后发布，
真实重建 next 计入 recovery；数据库 code 7 拒绝不重试。以上仍须新源码整轮云端复验。

## 补充的宿主错误边界

保留原 8 项专项，并增后续章节 XML 格式错误、真实章节 options 的 1 MiB workspace LIMIT、空阅读章三项。
每项检查已接受画面和页码不变、下一有效章不被跳入、进程重启仍在原位置；预算恢复 8 MiB 后须能打开同一目标章。
空阅读章当前明确不支持，返回可恢复错误；该项要求普通 UI 时限内结束且不崩溃、不循环，不宣称自动跳空章。
`review_chapter_budget` 只在 DEBUG 测试入口把预算传到真实 `exr_chapter_options`，不伪造 SDK 返回值。
以上新增项也必须在正式源码整轮验收，不转授 SDK 层测试的通过结果。

进度恢复的整章 point-selector 解析设真实 5 秒查询预算。耗尽后使用独立 unresolved-budget 状态（不是 FOUND/MISSING），
关闭可能已取消的 pager，再从原 part/path 打开新 pager，验证原章内偏移的 UTF-8 边界后明确 fallback。
原 selector 保留，恢复和字号变化不覆写；显式翻页才能保存新位置。标注解析没有此 fallback。
新增预算用例同时触发长章恢复的真实查询超时，比较公开 getter 返回 selector 的 SHA-256，验证恢复/字号前后一致、显式翻页后改变。
帧发布前无论是否保存进度均重新检查 DB source，跨 owner 提交造成失效时先重建，避免发布旧 source 的画面。

## 后续失败保留

`dafa5c4`／`39868073192` 与正式 `43ef432`／`39868542563` 都是原 45/45、新 8/8、review 9/10，
仍因 owner49 恢复超出原 20 秒观察窗拒绝；门禁未获验收。云端诊断 `39869524586` 表明打开约 4 秒、后续整章 selector 查询超时。
`2aa7db4fd5fb48f5b9f665c6160a86dd2a0d79e6`／`39869990335` 已同次达到 review 10/10、新专项 11/11、49/49/0（41734 ms），
但原 45 项的 PDF 重启帧比较失败，最终拒绝、48+16 不计通过。原件保留，不拼接此前已通过的 45 项。
接续在 PDF 重启参考捕获前增加“页面实际像素已变化”的原时限断言，保留重启前后裁剪 PNG 与散列/边界观测；
最终帧精确相等断言及 8 秒比较窗均不变，原 45 项标题、次序和标识保持不变。

## 首次完整通过

受测完整源码 `7b97041aca4053b27fd7d24f12d505ffc60d3e40`，SDK 来源为 `2f26847684b54006ca812c35477ceae43719e7d4`。
正式 run `39871797469`／attempt 1／job `120147731764` 全步骤 success：

| 检查 | 同次结果 |
| --- | --- |
| SDK、host 与两份测试 APK | 构建通过 |
| 原 walkthrough | 45/45，0 失败、0 跳过 |
| 独立 review | 10/10，0 失败、0 跳过 |
| bounded 专项 | 11/11，0 失败、0 跳过 |
| 真实顺序分页 | 49 页／49 native next／0 recovery，44729 ms |
| 原证据门禁 | 48/48，accepted=true |
| 附加 bounded 门禁 | 16/16，accepted=true |
| 最终 fail-closed 汇总 | accepted=true，problems=[] |

云端工件唯一一份 `EXReader-WP13-Android`，id `12467401242`，150877425 B，
digest `sha256:88f6e8be2454d102effff4ff0cb888fb519f7c4f0c0d1c313faf212d969d9089`，
API 确认同 run、同受测 SHA、非空、未过期，expires_at=`2027-01-20T23:26:32Z`。
包含 SDK、APKs、原始日志、66 项逐例 JSON/截图、48+16 门禁报告及 PDF 前后裁剪帧。

从 `2f268` 接续到正式 SDK `9c69` 仅有测试与冻结记录差异，SDK 受保护树相同。
本分支已合入 `9c69` 并只更新 SDK/ownership 双守卫及文档；按集成人调度，不重复单独 dispatch，等待共同 S 的整轮。
Android 所有权边界固定为 `797c47fc8d5c397fd7c960afe91eb6f851ec07f1`，是共同 S 的必需祖先；
差异范围从正式 SDK `9c69` 量到该边界，避免把后续 Apple 等包的合并错误归属给 Android。
边界后的本次提交仅固定工作流引用和交接文档，实际受测 source 仍由共同 S 的 Actions 身份和完整证据绑定。

# H10 Android bounded 候选

候选起点 `fd210224a4eba206762c08de435a5e9edfdf2a90`，SDK schema 7 API 已稳定；正式 K 与 Windows pilot 尚待集成人授予。
本分支实现 app-local JNI／Java，不修改 SDK 与共享 JNI。所有构建、测试、夹具、散列和证据处理在 Actions。

新导入 EPUB 走 package-only file import；去重后查询 storage mode。
bounded 书从同一书库 owner 的 `exr_library_source` 打开 publication/chapter pager，选文和 virtual nodes 只持有当前页文字窗口。
进度采用 part/path/章内 selector；恢复先 resolve，不精确时明确显示 stored-offset fallback 并保留原记录。
新 notes 使用独立 EPUB API，评论修改不重抓选区，导航只接受 FOUND。legacy EPUB／其他重排与 PDF/CBZ 保留原入口。

候选工作流 `r5-android-bounded-candidate.yml` 只验证候选 SDK/APK 能否构建，固定 `candidate_only=true, accepted=false`。
`ANDROID_CANDIDATE_SDK_BASE` 只用于候选来源检查，不替代正式 `SDK_BASE`；正式验收等待固定 K。
原 45+10 IDs、49 页／49 actual next／0 recovery、48 门禁不删减，新增专项及模拟器闭环仍须完整执行。

范围仍为 API 34 x86_64 模拟器，`physical_device_execution=false`；真机／签名／TalkBack 单独验收。

# H10：Android 有界书库阅读接入

执行 [共同约束](reading-extra-index.md#全部包共同约束)。准备可立即开始，正式实现等待固定 SDK
及 H8 闭环复核。以收到的完整 SDK SHA 建 `handoff/reading-h10-android`。
准备参考 B=`b529513b7e8e8992786f8c679c0ec6c92110b035` 与 [接入地图](../R5-NATIVE-HOST-ADOPTION.md)。

## 边界与工作

只改 `examples/android/`、Android 专用 build/check/evidence 工具、
`.github/workflows/wp13-android.yml`、`tests/android_host/`、`docs/WP13-ANDROID.md` 与本包证据。
不改共享 JNI/Java binding、SDK、schema 或其他平台。

1. 用宿主局部 `exreader_host_jni.c` 桥接冻结公共 API；EPUB `ReflowSession`
   不再复制全文 byte[]，PageSnapshot/ReaderView 只持有页面有限文本和几何。
2. `prepare/next/recoverAcceptedCursor` 保留候选接受/失败回滚，
   章内位置持久化与跨章顺序采用统一契约。
3. progress/saveProgress/notes 消除隐藏的 `exr_library_document` 全文重开；
   导入预检与书库导入也必须走有界入口。只有文件直接渲染不算书架大章闭环。
4. 保留 worker、HostTask、generation、取消和 app-owned 原件管理；
   虚拟无障碍节点和真实触摸选择不能因改分页路径退化。

## 云端出口

API34 default x86_64 模拟器，同源 SDK/APK 构建、原45项、独立10项、
原49页/49 native next/0 recovery、48项证据门禁与严格 accepted 继续通过。
新增跨章长章、内存逐出、字号/旋转/进程重开、取消换书、标注恢复等独立测试；
新增页面计量单独列出，不修改原49页预期以掩盖回归。
报告 bounded 路径、内存/位图/耗时原始观测及逐例工件身份。

真机/签名/TalkBack 及全格式扩充不在本包。遇到旧SDK保护树守卫拒绝新合法基线，
报主代理更新统一基线，不删除守卫。准备期只交映射与测试计划。

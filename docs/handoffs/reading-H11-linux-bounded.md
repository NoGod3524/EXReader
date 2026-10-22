# H11：Linux GTK 有界 EPUB 阅读接入

执行 [共同约束](reading-extra-index.md#全部包共同约束)。可先准备；正式实现等待固定 SDK
及 H8 闭环复核。收到完整 SDK SHA 后建 `handoff/reading-h11-linux`。
准备参考 B=`b529513b7e8e8992786f8c679c0ec6c92110b035` 和 [接入地图](../R5-NATIVE-HOST-ADOPTION.md)。

## 边界与实现

拥有 `examples/linux/`、Linux 宿主专用构建/检查工具和 workflow、
专用验收夹具、`docs/WP13-LINUX.md` 及本包证据。先核对现有实际文件名，
只修改对应 Linux 宿主文件，不碰阅读 preset 通用门禁、引擎、schema 或其他宿主。

- `open_id/frame/present/resize_font/save_progress/add_note/note_activated`
  接固定 EPUB publication/part bounded pager 与章内存储接口。
- GTK 回调中现有同步 SDK 调用移入一个串行 worker，提供取消和 generation；
  GTK 主线程仅更新自有位图和有限文字，关闭/换书不发布旧结果。
- GtkTextBuffer 只保存当页文字，选择范围按 UTF-8 字节映射；
  锚点、复制和标注不得偷偷重开全文档。
- 其他重排格式保持明确上限。本包不新增 Linux PDF/CBZ UI。

## 云端出口

保留原 Linux 宿主验收；云端有图形会话的自动化新增跨章双向翻页、长章逐出、
字号/窗口改变、关闭换书取消、进程重开位置、选文/复制/标注及歧义处理。
证明 GTK 主循环在长任务期间仍响应；保留输入/状态与程序身份，不把截图数量当响应证据。
分别报告 parse/page/checkpoint/bitmap/进程峰值，记录使用有界路径，禁止全文回退冒充完成。

交付完整 SHA、同源 run、逐例结果与工件身份；共享接口缺口交主代理。
准备期输出实际调用地图与验收计划，不实现草案接口。

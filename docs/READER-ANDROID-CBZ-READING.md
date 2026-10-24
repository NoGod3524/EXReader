# Android CBZ 产品页级位置

固定宿主起点 `91270f8e7b5a3085430992b97dd27f612666480a`，分支 `codex/reader-android-cbz-reading`。本轮仍待 Actions，不授予新增 CBZ 能力。

冻结 SDK `9854061be331fe603a1822d9b2b36ee357154927` 的 CBZ provider 实际调用 `exr_fixed_text_create("",0,NULL,0,...)` 返回真实空文本快照。旧 Android Reading 源码 `047648865e509d5835b7d6e1389681e314d94e28` 在宿主中显式拒绝该格式，不能据此断言 SDK 没有 text provider。本轮只接线，不改 SDK、冻结 bindings、模块树、schema 或同步 wire。

## 当前渲染器与来源

冻结 Java `FixedDocument` 不公开页 ID/anchor 或内部句柄。本包给启用 Reading 的 CBZ 增加 app-local `NativeCbz` 包装，仍在原 SDK worker / `exreader_host` DSO。它用已核字节打开公共 `exr_fixed_open_memory`，持有**实际绘制的同一个文档**；绘制、真实 `load_text`、页目录与公开 `fixed_anchor_resolve` 均操作该文档。未反射或修改冻结 Java SDK 的私有字段。

来源 key 由传入当前渲染器的实际原件字节 SHA-256 计算，打开前后与 SDK 原件/产品来源核对。每次捕获、定位、明确 restore、待确认精确重试均重新核对来源/key/parser。独立 library-source 文档和实际当前 renderer 文档都须公开 FOUND，且来源、页 ID、实际目录序号、范围与 selector 字节相同。定位后的实际帧再次核对页 ID；不向 current C resolve 传递旧 unit hint，更不按提示页号回退。

空 selector 只能来自公开 `fixed_anchor_create` 或其通过 G03/G04 保留的副本；NULL 与真实非NULL空字节保持不同。不存在的页 ID、NULL exact、显式 NUL、另一来源或变化的显示原件均保留真实拒绝/未命中。图像页不产生 OCR 文字或高亮范围。

## 产品边界

使用原“阅读记录”面板的页级书签和产品进度。保存/编辑/删除/明确历史 restore 不写 SDK notes/旧进度、不自动跳转。只有经双重 FOUND 的实际页面导航才按原宿主规则保存实际 SDK 页位置。持久请求仍由原 `ReadingRequests` 写出完整原参数、稳定 revision/entity/expected heads；真实提交后杀进程再确认必须精确复用请求，不新增 ID、不重新捕获或重排 outbox。

## 旧断言升级与云端出口

原 Reading16 中仅用例 `pdf_real_page_id_points_and_cbz_capture_refusal` 升级为 `pdf_and_cbz_real_page_id_points`：保留两份 PDF 正例，把已知错误宿主拒绝改成真实 CBZ 空快照/page-ID 捕获与 FOUND 正例。其他 missing/NUL/legacy/unsafe/stale/cancel/历史/真实 kill/retry 等断言不变。旧受测源码、拒绝结果与证据不改写。

新工作流 `reader-android-cbz-reading.yml` 保留原 SDK/transport/正式宿主16、Search15、Navigation18、升级后的Reading16、Preferences17，随后新增 CBZ8首进程+真实kill/retry1+再次重开1。独立预期由三页灰阶 `40/110/180`、`001.png/002.png/003.png` 在任何 SDK 读取前登记。验证实际 SDK 中心像素、真实空 snapshot、来源/页 ID、当前 renderer、错 hint、missing/NULL/NUL/foreign key、编辑/delete/明确 restore、取消、原件副本变化、真实旋转和提交后杀进程后的精确重试。

所有构建、语法检查、夹具、测试及工件解析仅 Actions。API34 `default` x86_64 模拟器以外、真机/TalkBack语音、OCR、产品性能、阅读页配色、平移及六平台完整产品仍独立跟踪。

# Android CBZ 产品页级位置

固定宿主起点 `91270f8e7b5a3085430992b97dd27f612666480a`，分支 `codex/reader-android-cbz-reading`。受测源码 `ee59f8f3aed6cf984cece4501bcac82795c115fd` 已通过 API34 `default` x86_64 模拟器整轮，授予本包声明的 CBZ 产品页级书签/进度接线范围。

冻结 SDK `9854061be331fe603a1822d9b2b36ee357154927` 的 CBZ provider 实际调用 `exr_fixed_text_create("",0,NULL,0,...)` 返回真实空文本快照。旧 Android Reading 源码 `047648865e509d5835b7d6e1389681e314d94e28` 在宿主中显式拒绝该格式，不能据此断言 SDK 没有 text provider。本轮只接线，不改 SDK、冻结 bindings、模块树、schema 或同步 wire。

## 当前渲染器与来源

冻结 Java `FixedDocument` 不公开页 ID/anchor 或内部句柄。本包给启用 Reading 的 CBZ 增加 app-local `NativeCbz` 包装，仍在原 SDK worker / `exreader_host` DSO。它用已核字节打开公共 `exr_fixed_open_memory`，持有**实际绘制的同一个文档**；绘制、真实 `load_text`、页目录与公开 `fixed_anchor_resolve` 均操作该文档。未反射或修改冻结 Java SDK 的私有字段。

来源 key 由传入当前渲染器的实际原件字节 SHA-256 计算，打开前后与 SDK 原件/产品来源核对。每次捕获、定位、明确 restore、待确认精确重试均重新核对来源/key/parser。独立 library-source 文档和实际当前 renderer 文档都须公开 FOUND，且来源、页 ID、实际目录序号、范围与 selector 字节相同。定位后的实际帧再次核对页 ID；不向 current C resolve 传递旧 unit hint，更不按提示页号回退。

空 selector 只能来自公开 `fixed_anchor_create` 或其通过 G03/G04 保留的副本；NULL 与真实非NULL空字节保持不同。不存在的页 ID、NULL exact、显式 NUL、另一来源或变化的显示原件均保留真实拒绝/未命中。图像页不产生 OCR 文字或高亮范围。

## 产品边界

使用原“阅读记录”面板的页级书签和产品进度。保存/编辑/删除/明确历史 restore 不写 SDK notes/旧进度、不自动跳转。只有经双重 FOUND 的实际页面导航才按原宿主规则保存实际 SDK 页位置。持久请求仍由原 `ReadingRequests` 写出完整原参数、稳定 revision/entity/expected heads；真实提交后杀进程再确认必须精确复用请求，不新增 ID、不重新捕获或重排 outbox。

## 旧断言升级与云端出口

原 Reading16 中仅用例 `pdf_real_page_id_points_and_cbz_capture_refusal` 升级为 `pdf_and_cbz_real_page_id_points`：保留两份 PDF 正例，把已知错误宿主拒绝改成真实 CBZ 空快照/page-ID 捕获与 FOUND 正例。其他 missing/NUL/legacy/unsafe/stale/cancel/历史/真实 kill/retry 等断言不变。旧受测源码、拒绝结果与证据不改写。

新工作流 `reader-android-cbz-reading.yml` 保留原 SDK/transport/正式宿主16、Search15、Navigation18、升级后的Reading16、Preferences17，随后新增 CBZ8首进程+真实kill/retry1+再次重开1。独立预期由原生成器三页 RGB `(40,80,215)/(110,80,145)/(180,80,75)`、`001.png/002.png/003.png` 在任何 SDK 读取前登记。验证实际 SDK 中心像素、真实空 snapshot、来源/页 ID、当前 renderer、错 hint、missing/NULL/NUL/foreign key、编辑/delete/明确 restore、取消、原件副本变化、真实旋转和提交后杀进程后的精确重试。

## 同源云端证据

[run 40143936053](https://github.com/NoGod3524/EXReader/actions/runs/40143936053)，attempt 1、job `121021215678`，整轮 success。原 SDK 导出、12 项真实同步 roundtrip、WebDAV 平台探针与 backend 91 + restart 4 均保留；Host16、Search15、Navigation18、升级后 Reading16、Preferences17 与新增 CBZ10 均为同一次、同源码通过。原 Preferences 页配色缺口仍为 `page_colors_accepted=false`。

| 项 | 原始观测 |
| --- | --- |
| CBZ 新检查 | first 8、真实提交后 kill/retry 1、再次重开 1，共 10/10 |
| 三个完成仪器化的进程 | `8088` / `8399` / `8503` |
| 原始截图与语义树 | 12 组 |
| 原件字节/散列复核 | 7 份 × 3 阶段，共 21 项 |
| 同一个首进程实际 renderer | `248283844`，实际绘制/读取/解析三页 ID `001.png`、`002.png`、`003.png` |
| 实际 ARGB / 独立预期 | `ff2850d7` / `ff6e5091` / `ffb4504b`，逐项严格一致 |
| 真实提交后终止 | PID `8271`，终止后为空 |
| 原持久请求 | 531 B，SHA-256 `20ead0cbf26068e70c93d942d3a611062e500cae1573c60f0d7e22df6ea69483` |
| 工件 | `12579788900`，145725410 B；SHA-256 `bc687d9a2b0e430db0b50eeee0f722221800b46421dd8ffc80d7824bdc421d6c` |
| 工件有效期 | `2027-01-22T23:44:13Z` |

独立 [只读 proof run 40144799161](https://github.com/NoGod3524/EXReader/actions/runs/40144799161)，source `234389f986f8ea8c83d1b8e3c6e0f8174c3469a6`、job `121023736911` success。该作业在 Actions 下载上述**原 ZIP**，核对 id/字节/完整 digest/有效期/同 run 与源码，再复核全部命名检查、报告、12 张 PNG、21 次原件散列、原持久请求和真实终止记录以及所有继承结果。另独立解压原 CBZ 的 PNG，逐块核对 CRC/IHDR、解压 IDAT 并逐像素核对三组 RGB。诊断本身保持 `diagnostic_only=true, accepted=false`；`codex/reader-android-cbz-reading-proof` 不合入。

## 保留的取消与失败

- `691f87dc` / run `40142671742`：源码复核发现误用了内部 `exr_fixed_anchor_validate`，在构建结论产生前取消；后续改为仅使用公开 `exr_fixed_anchor_resolve` 校验。原工件 `12578758748` 保留。
- `1530acb5` / run `40142712077`：所有继承套件通过，新 CBZ 第一项失败。原 PNG 生成器写 RGB `(shade,80,255-shade)`，测试却误登记成灰阶。后续按原生成器固定 RGB 修正预登记，像素仍要求严格相等，并新增实际/预期 ARGB 记录。生产 CBZ 实现未因该失败更改；原 144918238 B 工件 `12579139279` 保留。

完整 job、工件、逐项检查、实际页观测、来源身份及 proof 记录见 [reader-android-cbz-reading.json](validation/reader-android-cbz-reading.json)。最终交回提交与受测源码的差异仅为这两份证据文档。

所有构建、语法检查、夹具、测试及工件解析仅 Actions。API34 `default` x86_64 模拟器以外、真机/TalkBack语音、OCR、产品性能、阅读页配色、平移及六平台完整产品仍独立跟踪。

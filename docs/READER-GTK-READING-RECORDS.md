# GTK 阅读记录：G03/G04 原生接线

状态：GTK G03/G04 本包范围通过。完整共同源码 `98796b9bacea347c62baf6b5808122127093225c` 的 run `40135514002` 已完成；只有原两项阅读页配色检查失败，因此整轮为 failure、整体 `accepted=false`，本包 `reading_records_scope_accepted=true`。

## 固定输入

- 起点为 GTK Nav 文档 HEAD `1ad762a0b68372c56b712d0129be8129d38b651f`。
- 冻结 SDK `9854061be331fe603a1822d9b2b36ee357154927`，3.40.0 / ABI 1。
- 已审 G03 tree `cf067b8be378d4195817d1106b81f358579e2280`。
- 已审 G04 tree `9d30b6c54f61496010f647695dedd7ea7ab0c7c1`。
- 已审 reading-state codec 拆分 tree `60127ae75fbac918237b1c8584e0f7ac2e6130a4`；公开头不变。

## 宿主行为

阅读页的“Reading records…”按钮或 Ctrl+Shift+R 打开原生 GTK 对话框。产品进度、书签、标注文字属于产品修订与 outbox；原 SDK 笔记面板保持独立。

产品调用借用 `received_owner.revisions`，复用原 SDK worker、书库和产品库生命周期。G03/G04 可选构建默认关闭，开启时只链接安装后的模块。

进度和书签使用公开 SDK 的真实 point capture；高亮使用真实 UTF-8 选区；NOTE_TEXT 由 G03 保持原 selector、parser 与 anchor 版本。保存前私有 GKeyFile 请求原子落盘，保留原件身份、稳定 revision/annotation/bootstrap ID、完整 observed heads 与原 capture。事务开始后关闭对话框只丢弃界面响应；后续显式“Confirm original save”重放该请求，不重新 capture。清理请求核对自身 revision ID。

G04 每次调用在原 owner 打开并关闭 view，返回独立拥有的 32 行、2 MiB keyset 快照。界面区分本方向完成、还有后续与字节预算截停。SAFE 以外只显示真实图计数；SAFE tombstone 不显示正文。不默认选首行，不按时间选 head。

“Open location”重新读取当前 SAFE head/SHA，以独立公开 SDK 会话 resolve；FOUND 后再次在当前 SDK 会话核对相同路由与字节范围，才进入原 frame 接受与 COMMIT 流程。EPUB 章节坐标不与 legacy/global 混用；固定页以 page_id 寻址。PDF/CBZ 均使用公开 `exr_fixed_load_text` 实际返回的快照；真实空快照的页点照常交给公开 capture/resolve，不手填 selector，不以旧页号猜 FOUND。

恢复需明确选中历史版本并再次确认。历史通过公开 `revision_get` 沿原父关系读取，最多 128 节点、32 个可选版本、累计 2 MiB；达到任一上限明确显示列表未完整。独立 FOUND 后重新公开 capture，生成新 restore 修订。

## 云端检查

新工作流 `reader-gtk-reading-records.yml` 固定源码、SDK/schema 与模块 tree，保留原 G03/G04 安装后消费者、Search/Nav/F3、原 GTK/书架/metadata/collections/account、AT-SPI 与 settings 检查。专项覆盖原生控件、真实选区、正文编辑、删除/历史恢复、独立定位、产品锁失败与真实进程死亡后的原请求重放。

本地只读写源码与 Git。构建、语法检查、夹具、测试和工件处理均由 GitHub Actions 执行。

## 最终同源结果

受测源码 `98796b9bacea347c62baf6b5808122127093225c`，run [40135514002](https://github.com/NoGod3524/EXReader/actions/runs/40135514002) / attempt 1 / job `120996089136`；`workflow_dispatch`，`reading_diagnostic_only=false`。

| 范围 | 实际结果 |
| --- | --- |
| 原生阅读记录 UI | 30/30；含真实 CBZ 第二页的空快照 point 进度、书签与独立/current 双 FOUND |
| 阅读记录后端 | 261：首进程 64、真实重开重放 19、路由 37、非 SAFE 图与字节预算 141 |
| 固定 G03 / G04 | 1413 / 56；G03 21 场景、6 轮真实竞争 |
| 原 reading 消费者 | legacy 121；v2 116 检查、18 capture、17 FOUND / 1 AMBIGUOUS、错位 0 |
| Search | 安装消费者 264（34 场景）、后端 296、真实 UI 30 |
| Nav | 安装消费者 130（4 场景）、后端 58、真实 UI 29 |
| F3 | 安装消费者 20 场景 |
| 原账号与接收 | 46/46 |
| 原 GTK / 产品 UI | 105：原宿主 20、catalog 5、固定页 24、书架 14、metadata 15、collections 27 |
| 原隔离回归 / 定向 AT-SPI | 4 / 10 |
| settings | 35 项均执行，33 通过；下列两项失败 |

唯一失败为 `light_foreground_and_background_change_page_pixels` 与 `dark_theme_and_palette_change_page_pixels`。原始 RGB 记录仍显示页面空白边距为 `[255,255,255]`；SDK 未改，未复制 renderer 或重染 bitmap。其余步骤全部 success，未跳过保留套件。

工件 `reader-gtk-reading-records-40135514002-1`：ID `12577940620`，43,314,895 B，`sha256:2250a111678d9697d3bbda1ec03602fdcf34dddc2f0ee8abd3089cbd33d4a7a4`，有效至 `2027-01-22T21:44:05Z`。GitHub metadata 的 source/run 与本轮一致、未过期。实际应用 SHA-256 为 `eeb43f34439b780820b67e5dab0ddf965e4dda45d9f62dd3f4549c20d744aa22`；各原生专项报告与链接图一致，唯一实际 SQLite provider 为 `libreader_catalog_sqlite.a`。

## 已完成的诊断与保留失败

源码 `61bc8ac7b09954833de37fa2700745f816157070`，run `40134726495` / attempt 1 / job `120993709680` 为 success。原生阅读记录 26 项、Nav 真实 UI 29 项、阅读后端 64 + 19 + 27 + 141 项均通过；固定 G03 1413 项、G04 56 项、原 legacy 121 项及 18 个真实 v2 capture 同源通过。该轮不是完整保留套件，也仍有宿主自己的 CBZ 显式拒绝；该拒绝已在后续源码移除，不代表 SDK 缺少真实空 text 对象。

阅读记录专项实际覆盖进度、point 书签、UTF-8 高亮、保持 selector 的正文修改、删除与明确历史恢复、独立 FOUND 定位、SIGKILL 后原请求重放、事务开始后关闭父窗并真实重开、三种非 SAFE 图的正文隔离、2 MiB 明确截停和双向 keyset 翻页。

首次两轮因测试 profile 的 0755 权限被私有请求检查正确拒绝，修正夹具为 0700。其后一轮保留了两个相同快捷键跨模态导致 restore 请求未发送的探针失败。高亮失败最终定位为宿主在禁用主窗以后才读取选区；改为原生焦点和敏感性变化之前冻结真实 UTF-8 范围后通过。

后续 CBZ 源码的两次诊断 run `40135154048` / `40135435918` 中，阅读 UI 30 项及本包后端全部通过，但保留 Nav 的 9000 行快速取消观察没达到原断言：一次观察到 phase 2 后最终为 phase 3/code 0，另一次未捕获短暂的 phase 2。原 Nav 断言、预算与工件均未改写；完整同源 run `40135514002` 的 Nav 29 项全部通过。全部七次诊断失败及工件身份保留在验收 JSON。

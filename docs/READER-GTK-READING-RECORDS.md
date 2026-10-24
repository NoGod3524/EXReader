# GTK 阅读记录：G03/G04 原生接线

状态：开发候选，尚无本次源码的云端验收结果。整体 `accepted=false`；原两项阅读页配色失败继续保留。

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

本地只读写源码与 Git。构建、语法检查、夹具、测试和工件处理均由 GitHub Actions 执行。结果出来后按真实日志记录 source/run/attempt/job、工件身份与失败。

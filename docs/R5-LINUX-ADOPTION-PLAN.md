# H11 Linux GTK 有界 EPUB 接入计划

有界后端与异步 GTK 生产宿主已经实现并通过独立云端验收。
本轮 SDK 候选为 `9c69bc4c7efb0cff68ced27562709fe597189041`，已含超窗口 inline 单元递归修复。
此前 `ce5d664c9f76d0613df6d79b27568a7039c4a81e` 的 H11 和 Windows H8 pilot 记录继续保留。
范围是现有 GTK 重排宿主；不新增 PDF/CBZ UI，不引入 WebView。

## 当前调用链与最少替换

| 现有函数 | 接入方式 |
| --- | --- |
| `import_path` | EPUB 改用冻结后的 file/source unique import；其余重排格式保留现有 8 MiB 快照上限与错误提示 |
| `open_id` | 识别 bounded 模式，source→publication→part pager；旧记录保留显式兼容路径，不能在新模式失败后重开全文 |
| `frame` | 不再从 document 查询全书长度；分页/渲染在 worker，复制当页 range/UTF-8/位图后释放借用关系 |
| `present` | GTK 主线程只接自有页面结果；GtkTextBuffer 设置当页文字，不从全书指针切片 |
| `save_progress` | worker 捕获章内点并用新 progress 写入；设置文件只保留书 ID/字号，不另存一套位置真值 |
| `resize_font` | 创建候选 pager 并解析章内 selector，成功后替换已接受状态；失败不推进进度 |
| `refresh_notes` | 新模式查询独立 EPUB notes；行数据保留 note 类型域/ID/part/path，不把新 ID 交给旧删除接口 |
| `add_note`、`note_activated`、`delete_note` | 页文本的 GTK 字符位置转换为 UTF-8 字节，再加章内 page start；worker 捕获/解析 selector，新接口持久化 |
| `action` 的前后翻页 | 当前章结束后按 `in_reading_order` 进入下一章；回前章末页的查询在 worker 内可取消，不在 GTK 主循环扫描 |

## 所有权与响应

SDK 调用移入一个串行 worker，独占 library、font、publication、
pager、锚点与 SDK 临时对象；GTK 主线程持有控件和自有页面数据，不能访问 worker 的借用 layout。
任务只传入书 ID、generation、所需页/章及有限选择范围。取消、关闭及新任务使旧 generation 失效，
完成回调通过 GTK 主循环提交前再次核对；失败/取消保留已接受画面与位置。
候选 session 只有在 GTK 接受自有位图/文字并成功执行串行 `READER_COMMIT` 后才提升为当前位置。
保存失败保留 pending；F12 重试，期间阻止换书/关闭。Escape 不取消 SAVE，关闭等待 SAVE 完成。
字号调整与重启保留精确章内字节位置；选择器不唯一时明确显示偏移回退并保留原持久化记录。
标注只接受 `FOUND` 的精确解析，不把数字偏移冒充唯一匹配。

只保留当前章 pager 和轻量目录；当前页文字与位图都有明确容量限制。
源 ZIP 长度、UTF-16/GTK 字符数、页号均不能替代章内 normalized UTF-8 selector。
关闭时取消任务、等待 worker 释放 SDK 对象，再完成应用退出，避免 use-after-free。

## 云端接入与出口

沿用 `.github/workflows/wp13-linux.yml` 的 GTK3/Xvfb/Openbox/xdotool 环境、
`tools/build_linux_host.py`、`tools/check_linux_host.py` 和 `tools/check_linux_host_regressions.py`。
原用例及安装消费者继续运行，新增独立多章、长章、缓存逐出、进程重开、标注与换书取消用例。
验收驱动等待任务状态/generation 提交，不靠固定 sleep 猜页面就绪。

UI 响应需用长任务执行期间实际发送输入并观察状态提交证明；截图数量不是响应指标。
日志增加存储模式、part、章内 range、任务 generation 和内存观测，不泄露正文样本。
工件绑定 source/run/attempt、程序与字体散列。真实库关闭重开后再核对精确定位，
不让旧进程保留的 pager 或文字缓冲伪装成恢复。

`tests/linux_host/check_bounded_ui.py` 用打包的正常 GTK 程序执行独立多章、长章 65 次真实翻页、
窗口逐出、跨章标注、重复 spine 路由、删除原件后的新进程重开、缺章保帧，及真实长任务期间的
F2 响应/Escape 取消/后续换书。诊断文件只观察状态，不提供动作入口或测试延时。
同脚本要求冻结 SDK 是受测源码祖先，并逐项核对八条保护树的 Git 对象身份。
`bounded_backend.c` 保留独立安装后端检查；`notes_failure.c` 额外覆盖保存失败、pending 重试与保存屏障。

## 固定交付

受测源码 `6cb58962866c4f2223dfba0d21b6d36675cbfff1`，run `39872057413` attempt 2，
唯一 host job `120150277110` 全步骤成功。原 20 项、4 组回归（其中真实 GTK/后端故障 26 断言、
字体恢复负例在原第 13 项被拒绝）、H11 37 项和后端 82 断言在同一源码/运行通过。
异步版本已归并为唯一生产 `examples/linux/reader.c`，旧未编译宿主和临时 `reader_async.c` 已删除。
工件、测量值及保留失败见 `docs/validation/r5-linux-bounded.json`；集成后需在共同源码重跑本工作流。
同源 attempt 1 在任何用例开始前遇到 GTK 窗口映射超时；其工件保留，attempt 2 从构建开始整 job 重跑，
未修改生产宿主、窗口预算或断言。本轮真实长任务输入响应为 16.74 ms，65 次翻页及其余内存观测保持同一出口。

# C10 — GTK 五模块原生接入

固定起点 `d263ce5228838ac90c0a0dc13a5193d4a7739681`（候选，不是已验收 BASE）。分支 `codex/reader-wave3-c10`。

## 入口（全部是原生菜单项 / 原生对话框；默认书架与阅读页不增加控件）

| 功能 | 入口 | 原生控件 |
| --- | --- | --- |
| 标注导入 | More 阅读操作 → Reading tools → Import annotations… | 系统文件选择器 → 预览对话框（整文件校验后显示记录数、将新增数、未包含的历史、文件字节数）→ “Import annotations” 才逐项 receive，取消不写 |
| 字体库 | Reading tools → Reading font… | 系统文件选择器导入本地字体；列表内选择 → Use selected 用同一 owner worker 以新 lease 重排，成功后旧 pager 已替换才释放旧 lease；失败/取消先释放候选 pager 再释放新 lease，旧字体与画面不变；Remove 拒绝在用字体 |
| 原件导出 | Reading tools → Export original… | 系统目录选择器 → 真实原件逐字节写入（`<slug>--<sha>.txt`），重复导出报告“已存在”，不覆盖 |
| 跳转历史 | Reading tools → Back/Forward to previous/next position（Alt+←/→） | 打开、翻页、搜索/目录/records 真实落点在接受帧后记录；Back/Forward 先在独立会话证明 FOUND 再渲染，只有 READER_COMMIT 接受后才 `reader_jh_complete` 移动游标；空方向/另一本书/未接受不移动 |
| 同步状态 | Reading tools → Sync status… | 打开 Account and Sync，内嵌只读快照（阶段/原因/分片/待处理/冲突），无任何开始、取消、重试、确认控件；无会话时明确写“No sync session” |

## 接入方式

- 唯一共享入口 `apps/reader/desktop/gtk_feature_integration.cmake`（`-DEXR_READER_GTK_WAVE3=ON -DREADER_WAVE3_PREFIX=<installed>`），公共 `apps/reader/desktop/CMakeLists.txt` 未改。要求 compact 宿主与既有 account/records/search/navigation owner，且拒绝 raw3 家族。
- 源码：`examples/linux/wave3_ui.inc`（GTK 侧，只发命令）、`examples/linux/wave3_backend.inc`（唯一 SDK worker 侧，真实模块调用）、`reading.h`/`reading.c`/`reader.c`/`accounts_ui.inc` 的小钩子。
- 线程：全部经现有 `host_job` 队列；文件名/字体导入/原件导出/历史定位在 `READER_W3_*` 命令里由 owner worker 执行；字体 lease 与 history item 都随帧释放语义处理（`w3_pending_discard` 在候选 pager 释放之后）。

## G13 `shelf_tab_stops_named` 根因与修复

共同 run 40237525525 的真实 twice-cycle 记录显示：第一圈 `Import sources`（toggle button）有名，第二圈同位置读到空名；该控件当时只有一个符号标签 `"▾"`，名字靠构造时一次 `atk_object_set_name()`。

判定：**产品命名缺陷**，不是 AT-SPI 观察错误。控件本身没有可读文本，ATK 名一旦没有落到当前可访问对象上（GtkMenuButton 会在内部标签变更后重建/重发名称），平台能推导出的后备只剩箭头图像的空名——与 observed 的 `role=toggle button, name=""` 一致；同圈其它有文本标签的按钮从未出现空名。

两处修复（都不改断言、不加重试）：

1. 名字写进控件自己的可见标签 `"Import sources"`，不再依赖一次性 ATK 覆盖，任何一次名称推导都得到同一个非空名字；同时补 tooltip 说明它是导入入口。
2. `accessible_name_on_focus()`：菜单按钮获得键盘焦点时把当前名称重新发布一次（先复制再 `atk_object_set_name`），使每圈 Tab 到达都产生一次真实名称事件；用于 `Import sources` 与 `More reader actions` 两个 GtkMenuButton。

该修复在 OFF 宿主上由原 `tests/reader_gtk_receive/check_atspi_fixes.py`（十项）复核，测试包本身未改；compact 宿主上由原 45 项一并复核。

## 测试与产物

- `tests/reader_wave3_c10/guard.py`：固定 seed、自有路径、公共 CMake 与旧测试字节未改。
- `tests/reader_wave3_c10/backend.c`（既有）：owner 级真实 store/SDK/模块业务检查（历史、字体 lease 与回滚、原件导出、同步状态、预览与确认导入）。
- `tests/reader_wave3_c10/check_ui.py`：真实 GTK 指针/键盘/AT-SPI 端到端；标注文件由 owner backend 用真实导出模块生成，再经 UI 预览与确认导入。
- 保留：`tests/reader_gtk_compact/check_ui.py`（45 项，同一 compact 包）与 `tests/reader_gtk_receive/check_atspi_fixes.py`（G13 十项，OFF 包）。
- `.github/workflows/reader-wave3-c10.yml`：guard → linux（两个宿主、backend、三套 UI）→ authenticate（run/attempt/程序/包/工件身份）。

# C10 GTK 五模块原生接入与无名焦点修复

固定 seed：`d263ce5228838ac90c0a0dc13a5193d4a7739681`；分支 `codex/reader-wave3-c10`；
本包独占路径见 `tests/reader_wave3_c10/guard.py`（`examples/linux/`、
`apps/reader/desktop/gtk_feature_integration.cmake`、`tests/reader_wave3_c10/`、
`.github/workflows/reader-wave3-c10.yml`、`docs/reader-wave3-c10/`、`HANDOFF-RESULT-C10.md`）。
SDK/五模块/其他 owner/旧裁判均与 seed 逐字节相同，由 guard 用 git tree 身份证明；seed 不是已验收 BASE。

## 1. `shelf_tab_stops_named` 的真实失败与根因

真实失败（原 `check_atspi_fixes.py`，共同 run 40237525525 / attempt 1，job 121302192817，
source `96270a2b`）的 observed 值：

```
Import F1 / Import sources(toggle button) / Shelf F2 / … / Named book.txt
Import F1 / ""(toggle button)     / Shelf F2 / …
```

同一位置、同一控件、同一角色，第一圈有名字，第二圈 AT-SPI 读到空名。不是"断言太严"，
也不是重试能掩盖的抖动：

1. 控件是 `GtkMenuButton`（GtkToggleButton 子类），当时唯一的可见内容是把标签设成符号
   `"▾"`，再用 `atk_object_set_name()` 一次性覆盖成 `Import sources`。
2. GTK3 的按钮名有两条来源：`AtkObject::name`（只有那一次显式赋值）与
   `gtk_button_accessible_get_name()` 从子标签/子图像推导的后备。符号标签本身没有可读文本；
   一旦焦点查询拿到的是重建后的可访问对象（`AtkObject::name` 为空），后备只能落到箭头
   `GtkImage`，它的名字就是空串 —— 与 observed 的 `role=toggle button, name=""` 完全吻合。
   同一圈里其它按钮都有文本标签，因此从未出现空名；这也解释了为什么"只此一个控件"失败。
3. 结论：**这是产品命名缺陷**（一个只有符号的控件把自己的名字押在一次性的 ATK 覆盖上），
   AT-SPI 只是如实报告。修断言或统一重试都会把真实缺陷藏起来。

修法（`examples/linux/reader.c` 的 Import sources 控件）：把名字写进控件自己的可见标签
`"Import sources"`，不再调用 `atk_object_set_name()`。平台每次查询都能从标签推出同一个名字，
重建可访问对象也不会丢；同时补 tooltip 说明它是导入入口。控件仍是 `GtkMenuButton`，
菜单项、鼠标点击与键盘激活路径不变（`tests/reader_gtk_batch_import`、
`tests/reader_gtk_drop_import` 仍按 `Import sources` 名字点击）。

## 2. 五模块接入（全部真实用户流程）

`wave3_backend.inc`（SDK owner worker）与 `wave3_ui.inc`（GTK）通过 `reading.c`/`reader.c`
接入，只调用已安装的五个 0.1.0 包，不复制解析器/存储/SDK：

| 能力 | 后端 | UI |
| --- | --- | --- |
| 标注导入 | `reader_annotation_import_run`：整文件预检 → 逐条 receive；预览在 header 处取消，未写任何记录 | More → Reading tools → Import annotations…：文件选择 → 预览对话框（条数/字节/"尚未导入"）→ 显式 Import annotations 才提交 |
| 本地字体 | `rfl_open/import_file/font_open/lease_font/remove`：租约绑定 pager，提交后才切换，丢弃即释放 | Reading font…：列表（内置 + 已导入）、Add font file…、Use selected、Remove；in-use 与异常都拒绝且保留旧字体 |
| 原件导出 | `roe_create/roe_run`（owner gate 串行化 SDK） | Export original…：目录选择；字节同一性、重复不覆盖 |
| 跳转历史 | `reader_jh_open/commit/peek/complete`：只有 READER_COMMIT 接受过的落点才入历史；back/forward 必须先独立 resolve 到 FOUND | Reading tools 的 Back/Forward 项（无极小历史时不可用）+ Alt+←/→ |
| 只读同步状态 | `reader_sync_view_capture` + summary/rows：只读快照，不 start/cancel/retry | Sync status… 打开 Account and Sync，Sync view 只读展示 |

次序/生命周期要点：

- 字体租约与 pager 同生命周期：`pending_discard()` 先释放 pending pager 再释放候选租约；
  `linux_reader_close` 先 `pending_discard`、再 `session_free`、再 `w3_free`、最后 `exr_font_free`。
  失败帧只丢弃"已 peek 的历史项"，不动仍属于 pending 帧的租约。
- 历史/字体/导出/同步全部在同一个 worker 上执行，GTK 线程只发命令；同步状态借用
  `accounts.session`，账户 tick 在 `w3_sync_busy()` 期间不会析构会话。
- 默认界面不变：工具只在低频 More → Reading tools 里；没有新增 WebView、没有第二份 SDK/store。

## 3. 云端验证（全部 Actions）

`.github/workflows/reader-wave3-c10.yml`：

1. `source`：py_compile + `guard.py`（HEAD==GITHUB_SHA、seed 为祖先、diff 只在自有路径、
   保护树与 seed 同 tree 身份、11 条拒绝样例 + 7 条接受样例自检）。
2. `gtk`：安装 SDK 3.41.0 与全部 owner + 五个模块（同一前缀、同一 SDK）；构建
   **非 compact** 宿主（G13 十项、搜索/目录/records/导入原业务集）与 **compact** 宿主
   （compact45、五工具真实 UI）；产出两份实际 GTK 包；运行
   `reader-gtk-wave3-backend`（owner 级 5 大项）、`check_ui.py`（五工具真实 AT-SPI 十项）、
   原 `tests/reader_gtk_compact/check_ui.py`（45 项）、原 `check_atspi_fixes.py`（10 项）、
   原搜索/目录/records/批量导入 UI 驱动。
3. 证据：同 run/attempt 的日志、两份包与 `build.json`、`result.json`、AT-SPI 树与截图。

未执行/未授予：完整 G13 审计与 Orca、Windows/Apple/Android、D13/D15–D20、S19 helper
（其链接闭包尚未通过，本包不冒用）、PR/tag/Release/默认分支。

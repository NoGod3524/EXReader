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

同一位置、同一角色在两圈返回不同名字，这是已确认的失败现象。
旧实现已有显式 ATK 名；GTK3 上游 `gtk_button_accessible_get_name` 会优先返回
该名字。因此此前“焦点导致 accessible 对象重建”的解释未经证实，不能作为根因结论。

当前保留可读文本标签 `Import sources`，并明确设置同名 ATK 名，使可见名称与
辅助技术名称一致。移除仅在已有非空名时重新赋同名的 focus 回调：该回调既不能
恢复空名，也没有证据说明它修复了旧失败。原 G13 断言保持原样，新的 Actions 观测
负责区分产品实际名称与 AT-SPI 读取/缓存异常；未通过前不声称 G13 修复完成。

上游依据：
https://github.com/GNOME/gtk/blob/gtk-3-24/gtk/a11y/gtkbuttonaccessible.c
（get_name 优先显式名，notify::label 仅处理未显式命名时的标签派生通知）。
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

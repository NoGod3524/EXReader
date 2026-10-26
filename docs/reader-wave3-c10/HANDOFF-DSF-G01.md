# GTK 五模块 C10 收尾交接（DSF-G01）

独立 GTK 收尾任务的交接记录。起点 `36d5deec`，分支 `codex/dsf-gtk-export-close`。
本文件只记录真实 Actions 结果；本机未运行任何构建、测试、语法检查、夹具、截图、benchmark
或工件下载/解包/解析。

## 1. 范围

沿用 `4561ef73` 的十项真实 GTK 用户流程（本队 `tests/reader_wave3_c10/check_ui.py`）与全部保留套件，
只修复"原件导出"在原生 SELECT_FOLDER 目录表里的定位失败，并让后续 history / sync 两项真实跑完。
不改产品代码、不改 SDK、不改保留驱动、不放宽任何断言与预算、不新增根目录文档。

## 2. source / run / attempt

| 项目 | 值 |
| --- | --- |
| 上一轮实际受测 source | `4561ef738e073058c900b176062c2d95ae7c5a19` |
| 上一轮 run / attempt | `40279255603` / `1`（failure） |
| 本队起点 | `36d5deec`（分支 `codex/dsf-gtk-export-close`） |
| 本轮完整 C10 验收 source | 由第 5 节回填（提交修复后发起，attempt `1`） |
| 本轮 workflow | `.github/workflows/reader-wave3-c10.yml`（未改动；`workflow_dispatch -r codex/dsf-gtk-export-close`） |

## 3. 唯一修复：原生目录行先进入视口，再点击

### 3.1 根因（GTK 3.24 源码，不是驱动猜测）

`gtk/a11y/gtktreeviewaccessible.c` 的 `gtk_tree_view_accessible_get_cell_extents()`：
宽度/高度永远取自 `gtk_tree_view_get_cell_area()`，而 x/y 只在 `is_cell_showing()` 为真时
才赋值，否则写 `G_MININT`：

```c
  *width = cell_rect.width;
  *height = cell_rect.height;
  if (is_cell_showing (tree_view, &cell_rect)) { *x = cell_rect.x + w_x; *y = cell_rect.y + w_y; }
  else { *x = G_MININT; *y = G_MININT; }
```

`is_cell_showing()` 把单元矩形与 `gtk_tree_view_get_visible_rect()` 比较。Home 目录表里
`work` 是字母序末尾的第九行，落在可见区之外 ⇒ x = y = -2147483648，而宽度仍是真实值
（约 1070px），中心点 = -2147483648 + 535 = **-2147483313**，正是上一轮送进 `xdotool` 的数字。

旧驱动只断言 `width > 0 and height > 0`；GTK 对单元**始终**设置 `ATK_STATE_SHOWING`
（只要 tree widget 已 mapped，见 `gtkcellaccessible.c` 的 `gtk_cell_accessible_ref_state_set()`）
和真实宽高，所以旧断言必然通过，缺陷一路走到 `xdotool mousemove` 才炸成
`unrecognized option '-2147483313'`。

### 3.2 修复路径（真实原生 AT-SPI 滚动 + 可见选中）

1. 单元自身的 AT-SPI Component `grab_focus()` ⇒ `gtk_tree_view_accessible_grab_cell_focus()` ⇒
   `gtk_tree_view_set_cursor_on_cell()` + `gtk_widget_grab_focus(tree)` + `gtk_window_present()`，
   即 GTK 自带的 scroll-to-cell 揭示路径（与保留的 folder-import 驱动同一条路，该驱动在
   run 40279255603 里已经真实走过 Home → build → fixtures 全链）。
2. 只接受 GTK **自己**给出的非哨兵矩形：x/y ≥ 0、宽高 > 3，且点击中心落在所包围的原生
   `table`（`ancestor(cell, {'table'}, dialog)`）之内；哨兵矩形一律不点。
3. 选中用 AT-SPI 状态确认：`gtk_tree_view_accessible_get_renderer_state()` 把
   `GTK_RBNODE_IS_SELECTED` 映射成 `GTK_CELL_RENDERER_SELECTED` ⇒ 单元的 `ATK_STATE_SELECTED`
   （`state_map` 直连），所以 `bus.states(row).get('selected')` 是真实选中位，不是推断。
   原断言保持原样。
4. 进入父目录的双击也走同一套"先验证视口、再真实点击"，不再直接读一次 extents 就点。
5. `click_node()` 的几何断言加严为 `x >= 0 and y >= 0`，并把节点名与矩形写进失败信息：
   这类哨兵坐标再也不会静默传给 `xdotool`。

明确没有做的事：没有加 `xdotool --`、没有夹紧/修改坐标、没有模糊或按序号选择、没有放宽
既有超时（chooser 关闭 30s、`wait_nodes` 20s、`wait_wave` 45s 全部不变）、没有删除任何断言。
新增的 25s 只存在于"行进入视口"这一新等待上，超时会带着 before/now/table/focus 四个实测值失败。

## 4. 具体业务结果

本节由第 5 节的真实 Actions 结果回填（状态：**待本轮运行**）。

| 项目 | 期望 | 实际 |
| --- | --- | --- |
| source guard / 冻结路径 | 通过 | 待填 |
| SDK、全部模块、两种 GTK 宿主与打包 | 通过 | 待填 |
| desktop ctest | 4/4 | 待填 |
| 五模块 owner probe | 114 断言 | 待填 |
| compact45 / G13 十项 | 45 / 10 | 待填 |
| search / navigation / records / batch / drop | 30 / 29 / 30 / 27 / 20 | 待填 |
| 五模块真实 UI 第 8 项（原件导出，逐字节） | 通过 | 待填 |
| 五模块真实 UI 第 9 项（history 前后） | 通过 | 待填 |
| 五模块真实 UI 第 10 项（sync 只读） | 通过 | 待填 |
| authenticate | 通过 | 待填 |

## 5. 原 ZIP 与实际程序身份（Actions 内解析）

**上一轮（`4561ef73`，run `40279255603` / attempt `1`）**，由该轮 authenticate 作业在 Actions 内
解析，本机未下载：

- 原 ZIP artifact id `12632725811`，name `reader-wave3-c10-40279255603-1`，
  99,314,481 bytes，SHA256 `03f2fef3820c41ba125bfc5eacce8a2af84e9dc5304ec5cd38766f877a2db20c`，
  到期 `2027-01-24T06:20:35Z`；实测 SHA256/字节数与 GitHub API digest/size 一致。
- 另存包装件 id `12632625994`（其内 `c10-original.zip` 才是上面那份，包装 ZIP 的 digest 不可混用）。
- 实际程序：
  compact `c10-compact-package/EXReader-Linux/bin/exreader-linux`
  = `7742a3b339863729ba20281200fb45a5ecd551ce51aab1c98b6ba540516979f6`；
  noncompact `c10-package/EXReader-Linux/bin/exreader-linux`
  = `09d7f28dca5f276a956f8c40a478e7325c0ebf729a5a26984e18fdd8a83fed90`。
- 该轮 identity 报告 `12632755840` 的 verified=false，原因正是五模块 UI scope 未通过；
  两程序 SHA256 与本次修复无关，**不能**替代本轮结果。

**本轮**：待本轮 authenticate 作业在 Actions 内解析后回填（ZIP id/size/digest/到期、两程序 SHA256、
identity.json 的 verified 与 problems）。

## 6. 仍未通过 / 未测

- 上一轮未执行的三项（导出/history/sync）在本轮之前一直是**未测**，不能算业务通过。
- 原 1710 项与 CPU 整体预算未重跑；完整 G13/Orca/真实读屏未覆盖。
- 真机、其余五个平台、带真实网络会话的 sync 状态均未覆盖。
- history 仍拒绝跨书跳转；annotation 导入沿用模块 heads-only 合同，不恢复缺失祖先。
- `G13` 旧 run `40237525525` 里 `shelf_tab_stops_named` 读到空名的原始根因仍未证明
  （后续两轮均读到 `Import sources`）。
- 本交接不宣称 GTK 五模块之外的产品完成，也不宣称六平台完成。

## 7. 最小 diff

本轮只改一个源码文件（`+80 / -7`）：

| 文件 | 改动 |
| --- | --- |
| `tests/reader_wave3_c10/check_ui.py` | 新增 `ancestor/centre/points_into/visible_cell/cell_click`；chooser 的 SELECT_FOLDER 分支改用"原生揭示 + 视口判定 + 真实点击 + ATK 选中确认"；`click_node` 拒绝哨兵坐标；导出项 observed 增加 `folder_selection` 证据 |
| `docs/reader-wave3-c10/HANDOFF-DSF-G01.md` | 本文件 |
| `docs/reader-wave3-c10/TEAM24-VALIDATION.md` | 追加收尾轮登记（不改旧记录） |

`.github/workflows/reader-wave3-c10.yml` 未改：`workflow_dispatch` 已存在，直接
`gh workflow run reader-wave3-c10.yml -r codex/dsf-gtk-export-close`，旧 `push` 触发的含义不变。
守卫范围（`tests/reader_wave3_c10/guard.py`，seed `d263ce52`）未动：SDK、五个模块、其他 owner、
原测试驱动、其他 workflow 仍必须是 seed 字节。

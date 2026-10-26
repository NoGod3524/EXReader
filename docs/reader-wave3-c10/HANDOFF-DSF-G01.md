# GTK 五模块 C10 收尾交接（DSF-G01）

独立 GTK 收尾任务的交接记录。起点 `36d5deec`，分支 `codex/dsf-gtk-export-close`。
本文件只记录真实 Actions 结果；本机未运行任何构建、测试、语法检查、夹具、截图、benchmark
或工件下载/解包/解析。

## 1. 结论先行

- 五模块真实 GTK UI **十项全部通过**（含上一轮未执行的原件导出、history、sync），
  `accepted=true`，报告 10/10 PASS。
- 本轮整轮仍为 **failure**，原因不在五模块：两条**保留**套件（`navigation`、`batch_import`）
  在真实 X11 上各自出现一次时序失败，**原样保留**，未修、未重跑、未开第二轮。
- `authenticate` 因此正确拒绝绑定（`AssertionError('navigation scope did not pass')`）。
  所以本阶段仍**不能**标记 GTK 五模块端到端验收完成，也不能宣称六平台产品完成。

## 2. source / run / attempt

| 项目 | 值 |
| --- | --- |
| 上一轮实际受测 source | `4561ef738e073058c900b176062c2d95ae7c5a19`（run `40279255603` / attempt `1`，failure） |
| 本队起点 | `36d5deec`（分支 `codex/dsf-gtk-export-close`） |
| 本次完整 C10 验收 source | `0be6a226540a8d54e6aa25ac2bf74cbc44d9971e`（提交修复后发起） |
| run / attempt | `40350391595` / `1`，整轮 failure |
| workflow | `.github/workflows/reader-wave3-c10.yml`（**未改动**；`gh workflow run reader-wave3-c10.yml -r codex/dsf-gtk-export-close`） |

本轮运行以 `0be6a226` 为 source。之后仅有 docs 提交（本文件与台账）回填结果，不改被测 source、
不触发新的 workflow（该分支没有 push 触发）。

## 3. 唯一修复：原生目录行先进入视口，再点击

### 3.1 根因（GTK 3.24 源码，不是驱动猜测）

`gtk/a11y/gtktreeviewaccessible.c` 的 `gtk_tree_view_accessible_get_cell_extents()`：
宽度/高度永远取自 `gtk_tree_view_get_cell_area()`，x/y 只在 `is_cell_showing()` 为真时才赋值，
否则写 `G_MININT`：

```c
  *width = cell_rect.width;
  *height = cell_rect.height;
  if (is_cell_showing (tree_view, &cell_rect)) { *x = cell_rect.x + w_x; *y = cell_rect.y + w_y; }
  else { *x = G_MININT; *y = G_MININT; }
```

`is_cell_showing()` 把单元矩形与 `gtk_tree_view_get_visible_rect()` 比较。Home 目录表里 `work`
是字母序末尾的一行，落在可见区之外 ⇒ x = y = -2147483648，而宽度仍是真实值（约 1070px），
中心点 = -2147483648 + 535 = **-2147483313**，正是上一轮送进 `xdotool` 的数字。

旧驱动只断言 `width > 0 and height > 0`；GTK 对单元**始终**设置 `ATK_STATE_SHOWING`
（只看 tree widget 是否 mapped，见 `gtkcellaccessible.c` 的 `gtk_cell_accessible_ref_state_set()`），
并始终给出真实宽高，所以旧断言必然通过，缺陷一路走到 `xdotool mousemove` 才炸成
`unrecognized option '-2147483313'`。

### 3.2 修复路径（真实原生 AT-SPI 滚动 + 可见选中）

1. 单元自身的 AT-SPI Component `grab_focus()` ⇒ `gtk_tree_view_accessible_grab_cell_focus()` ⇒
   `gtk_tree_view_set_cursor_on_cell()` + `gtk_widget_grab_focus(tree)` + `gtk_window_present()`，
   即 GTK 自带的 scroll-to-cell 揭示路径（与保留的 folder-import 驱动同一条路）。
2. 只接受 GTK **自己**给出的非哨兵矩形：x/y ≥ 0、宽高 > 3，且点击中心落在所包围的原生
   `table`（`ancestor(cell, {'table'}, dialog)`）之内；哨兵矩形一律不点。
3. 选中用 AT-SPI 状态确认：`gtk_tree_view_accessible_get_renderer_state()` 把
   `GTK_RBNODE_IS_SELECTED` 映射成 `GTK_CELL_RENDERER_SELECTED`，再经 `state_map` 成为单元的
   `ATK_STATE_SELECTED`，所以 `bus.states(row).get('selected')` 是真实选中位。原断言保持原样。
4. 进入父目录的双击也走同一套"先验证视口、再真实点击"，不再读一次 extents 就点。
5. `click_node()` 的几何断言加严为 `x >= 0 and y >= 0`，失败信息带节点名与矩形：这类哨兵坐标
   再也不会静默传给 `xdotool`。

明确没有做的事：没有加 `xdotool --`、没有夹紧/修改坐标、没有模糊或按序号选择、没有放宽既有
超时（chooser 关闭 30s、`wait_nodes` 20s、`wait_wave` 45s 全不变）、没有删除任何断言。
新增的 25s 只用于"行进入视口"这一新等待，超时会带 before/now/table/focus 四个实测值失败。

### 3.3 本轮实测的揭示证据（Actions 日志原文）

```json
{"native_row_visible": "c10-wave3-ui", "reveal": true,
 "before": {"x": -2147483648, "y": -2147483648, "width": 671, "height": 21},
 "after":  {"x": 360, "y": 2170, "width": 671, "height": 21},
 "table":  {"x": 330, "y": 1463, "width": 939, "height": 729}, "selected": true}
```

同一套路径依次走完 `work → EXReader → EXReader → build → c10-wave3-ui → exported`，
每一步都打印 before/after/table/selected；`work`、`EXReader`、`build`、`exported` 在
`635×21``/`671×21` 行高下坐标合法，只有 `c10-wave3-ui` 需要真实滚动（before 就是 G_MININT）。

## 4. 具体业务结果（run 40350391595 / attempt 1）

| 范围 | 实际结果 |
| --- | --- |
| 自有路径与冻结 guard | 通过（`changed` 仅本队路径） |
| SDK、全部模块安装 | 通过 |
| 两种 GTK 宿主构建与打包 | 通过 |
| desktop ctest | `100% tests passed, 0 tests failed out of 4` |
| 五模块 owner probe | 18 组 `{"check":…,"pass":true}`（114 条 REQUIRE 全过） |
| 原 compact45 | 通过，`{"accepted": true, "checks": 45, "failure": null}` |
| **五模块真实 UI（十项）** | **10/10 PASS，`accepted=true`** |
| ├ 第 8 项 原件导出 | PASS：`build/c10-wave3-ui/exported/historytxt--ab723a4beadcbe33a99be5e98ba58b886b96f78932e3bf27e3aa436d050c7d3b.txt`，89,048 bytes，`parent == exported`，`created=1`，`durable=1`，与源文件逐字节相等 |
| ├ 第 9 项 history | PASS：真实搜索落地后 `count=2, cursor=1, moves=2`；`landing_start=11770 → back=388 → forward=11770`，边界 back/forward 使能逐项正确 |
| └ 第 10 项 sync | PASS：`refreshes=1, phase=4`，文本 `No sync session is active in this window…`，关窗重开文本一致（AT-SPI 读取 107 字符），`editable=false`，`session_present=0`、`session_state=0` |
| 原 G13 十项 | 通过，`accepted=true`（`shelf_tab_stops_named` 读到 `Import sources`） |
| 原 search | 30/30 通过 |
| 原 reading records | 30/30 通过 |
| 原 drop UI | 20/20 逐项 `passed:true` |
| 原 navigation | **失败**：前 22 项通过，第 23 项 `active_directory()` 15s 超时 |
| 原 batch import | **失败**：前 14 项通过，第 3 次 `choose()` 在 `element('EXReader')` 15s 超时 |
| authenticate | failure：`AssertionError('navigation scope did not pass')`，未绑定五模块 UI scope |

### 4.1 两条保留套件的失败（原样保留，不修不重跑）

两者都在 `tests/reader_gtk_navigation`、`tests/reader_gtk_batch_import`——**受 guard 保护、
本轮 diff 未触碰**的保留驱动，且与上一轮 `4561ef73`（同一份字节、同样环境）通过的结果不同，
属真实 X11 上的时序竞争，不是产品 owner 返回失败：

1. **navigation 第 23 项**（`check_ui.py:190` `active_directory()`）：15s 窗口到期时观测文件为
   `visible=1, running=0, phase=3, polls=40, actions=32, total=9000, next=32`。
   驱动要求抓到**瞬态** `phase=='2' and polls>0`；本轮 9000 条目录扫描确实执行了（polls=40）并
   很快推进到 `phase=3`，采样窗口错过，判超时。原始失败（`phase=3/polls=40`）已保留在日志中。
2. **batch import 第 3 次 `choose()`**（`check_ui.py:144`）：异常时驱动自行 dump 的原生选择器为
   `$HOME`（路径条 `runner`，行 `actions-runner`、`work`…），`work` 行状态
   `selected+focused+active`，`Choose folder` 敏感 ⇒ `xdotool click --repeat 2` 的双击没有产生
   目录跳转，列表未变成 `/home/runner/work`，下一层 `EXReader` 行不存在而 15s 超时。
   该保留驱动对"进入父目录"没有独立断言，因此表现为缺控件。

同一步骤里 `search 30`、`records 30`、`drop 20` 全部通过；五模块 UI 十项在其前一个独立
`xvfb-run` + `dbus-run-session` 步骤里已 10/10 通过。按协调者指令，本轮失败原样保留，
**未再发起第二轮完整验收**，也未修改受保护的保留驱动来掩盖失败。

## 5. 原 ZIP 与实际程序身份（全部在 Actions 内解析）

**本轮（`0be6a226`，run `40350391595`）：** 由该轮 authenticate 作业在 Actions 内解析
（`tests/reader_wave3_c10/identity.py`），本机未下载、未解包：

- 原 ZIP artifact id `12664682969`，name `reader-wave3-c10-40350391595-1`，
  **99,382,842 bytes**，digest `sha256:70eff07ec8c419af4568dc438dcd24d1e3f1aa1bc5cecff878b7884d9002d23f`，
  到期 `2027-01-24T15:32:55Z`，`expired=false`；`--archive` 实测 ZIP 的 SHA256 与字节数
  与 GitHub API digest/size 一致（该断言先于报告绑定执行并通过）。
- 实际程序（包内真实二进制）：
  compact `c10-compact-package/EXReader-Linux/bin/exreader-linux`
  = `7742a3b339863729ba20281200fb45a5ecd551ce51aab1c98b6ba540516979f6`；
  noncompact `c10-package/EXReader-Linux/bin/exreader-linux`
  = `09d7f28dca5f276a956f8c40a478e7325c0ebf729a5a26984e18fdd8a83fed90`；
  `c10-desktop/reader-gtk-drop-backend` = `bc8885df4e805cd218d5db13862e18f08e942a03d79ccbddf6228fc64204243d`；
  `c10-desktop/reader-gtk-drop-native-source` = `084b2a30e04322d35e4ba9c6ad4f24f3e2f4a09a494c0f1604d77096b125fa15`。
- 五模块 UI 报告自报的 `program_sha256` = `7742a3b3…516979f6`，即 compact 包真实二进制，
  与上表的 `wave3` 程序身份一致；`source_sha/run_id/attempt` 均为本轮的
  `0be6a226…` / `40350391595` / `1`。
- `identity.json` 的 `verified=false`，`problems=["AssertionError('navigation scope did not pass')"]`。
  wave3_tools、compact45、g13_ten、search 四份报告的 source/run/attempt、`program_sha256`
  与"每条 check 均 pass"断言在失败前均已通过；navigation 起未再绑定。

**上一轮（`4561ef73`，run `40279255603` / attempt `1`）**，同样由 Actions 内解析：

- 原 ZIP artifact id `12632725811`，99,314,481 bytes，
  SHA256 `03f2fef3820c41ba125bfc5eacce8a2af84e9dc5304ec5cd38766f877a2db20c`，
  到期 `2027-01-24T06:20:35Z`；另存包装件 id `12632625994`（其内 `c10-original.zip` 才是这一份，
  包装 ZIP 自身 digest 不可混用）。
- 两程序 SHA256 与本轮相同（`7742a3b3…` / `09d7f28d…`）：修复只改驱动，未改产品二进制。

## 6. 仍未通过 / 未测

- 本轮整轮 failure 的唯一原因是 `navigation`、`batch_import` 两条保留驱动各一次时序失败；
  因此 `authenticate` 未通过，五模块 UI 的 10/10 不能单独当作整轮验收完成。
- 原 1710 项与 CPU 整体预算未重跑；完整 G13/Orca/真实读屏未覆盖。
- 真机、其余五个平台、带真实网络会话的 sync 状态未覆盖（本轮 sync 为无会话只读快照）。
- history 仍拒绝跨书跳转；annotation 导入沿用模块 heads-only 合同，不恢复缺失祖先。
- `G13` 旧 run `40237525525` 里 `shelf_tab_stops_named` 读到空名的原始根因仍未证明
  （本轮与上一轮均读到 `Import sources`）。
- 本交接不宣称 GTK 五模块验收完成，更不宣称六平台产品完成。

## 7. 最小 diff

本轮只改一个源码文件（`+80 / −7`）：

| 文件 | 改动 |
| --- | --- |
| `tests/reader_wave3_c10/check_ui.py` | 新增 `ancestor/centre/points_into/visible_cell/cell_click`；SELECT_FOLDER 分支改为"原生揭示 → 视口判定 → 真实点击 → ATK 选中确认"；`click_node` 拒绝哨兵坐标；导出项 `observed` 增加 `folder_selection` |
| `docs/reader-wave3-c10/HANDOFF-DSF-G01.md` | 本文件 |
| `docs/reader-wave3-c10/TEAM24-VALIDATION.md` | 追加收尾轮登记（旧记录不改） |

`.github/workflows/reader-wave3-c10.yml` 未改（用既有的 `workflow_dispatch`），旧 `push` 触发含义不变；
`guard.py`（seed `d263ce52`）未动：SDK、五个模块、其他 owner、原测试驱动、其他 workflow 仍是 seed 字节。

## 8. 复现

```
gh workflow run reader-wave3-c10.yml -r codex/dsf-gtk-export-close
```

五模块 UI 单步等价命令与 workflow 相同；十项断言、`--book`/`--annotations`/`--font` 夹具、
`exported` 目标目录与逐字节比较均未改变。

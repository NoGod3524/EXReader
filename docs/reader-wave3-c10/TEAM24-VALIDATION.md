# GTK team24 验收记录
阶段已封存，**未通过 GTK 五模块完整验收**。
最后受测 source：`4561ef738e073058c900b176062c2d95ae7c5a19`；
[run 40279255603 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40279255603)：failure。
本队初始两轮加协调者明确批准的一轮均已结束，不再启动第四轮。


团队起点：`05c8494eb8320c22b9e7b439cca82e21bc36a461`，分支 `codex/team24-gtk`。原 C10 guard 的 seed 仍为 `d263ce5228838ac90c0a0dc13a5193d4a7739681`；本轮没有重置旧失败记录或放宽 SDK、原 1710 项及 CPU 预算。

## 保留的先前执行

| run / attempt | source | 实际结果 |
| --- | --- | --- |
| 40237525525 / 1 | 96270a2b478b673eb45b7e2467e2e2acb6b64a88 | 共同 GTK 轮次失败：G13 `shelf_tab_stops_named`；后续身份认证失败保留 |
| 40273627779 / 1 | 5892edd76b6d4919cf4e1f3d57f6c20e8ad75dc0 | C10 失败 |
| 40274220118 / 1 | bb82933ef9e9e5ad43ccaf3cfc398fcdf8bbad47 | C10 取消 |
| 40274396894 / 1 | 05c8494eb8320c22b9e7b439cca82e21bc36a461 | C10 失败：session 在 sync 安装前配置，找不到 EXReaderSync；未产出程序，认证随之失败 |

截至 team24 开始读取时，上述运行均已结束。team24 允许的新完整轮次另计，最多两次；只有父代理提交并启动完整 Actions。

## 本队补充的验收

- 后端真实 owner probe：字体候选取消后释放 lease、候选字体可删除、旧阅读器仍能产生并接受下一页；标注取消丢弃预览，确认绑定已检查的 snapshot，即使原路径文件随后被修改也不会导入另一份未检查的内容。
- 真实 GTK UI：保留现有十项五模块流程；字体文件异常后比较 book/part/page/start/end/frame_generation，随后真实 Next/Previous 验证阅读可用；同步只读详情关闭再打开须保持文本；预览对话框须为模态且持有焦点。
- 原 GTK compact45、G13 十项、搜索、目录、阅读记录和批量导入 driver 保持原字节。身份检查要求每份报告的业务通过字段、source/run/attempt、实际程序 SHA256 一致，拒绝 diagnostic-only 报告。
- `g13_diagnostic.py` 包装原 G13 driver；原 `bus.name` 返回值原样送进原断言。空名 focused toggle 的直接 AT-SPI 读取、异常和独立 raw D-Bus focused Name 留档，不清 cache、不把诊断重读值用于通过断言。与宿主焦点时 ATK 名称日志对照定位产品或观察问题。
- Actions 取得本轮原 ZIP 后，identity 的 `--archive` 核对 ZIP 实际 SHA256 与 GitHub API digest、实际字节数与 API size；再核对两个打包程序和七份业务报告。

本机未运行构建、测试、语法检查、生成夹具、截图、benchmark 或工件下载/解包/解析。新增断言是否通过必须以新 Actions 结果填写；此文档不宣称六平台完成、真机验证或真实读屏验收。

## team24 新轮次

以下逐轮登记真实 source、run/attempt、各 job 结论与产物；旧失败不重置。

### 新第 1 轮（已完成，失败）

source `a34fb18660244e0e6db121035b1ae99193b0b297`；run `40275931138` / attempt `1`。
源码范围/冻结检查通过；SDK、所有模块、非紧凑与紧凑 GTK 宿主构建和打包、desktop ctest 通过。
夹具步骤调用不存在的 `tests/reader_gtk_search/make_search_fixtures.py` 后失败；GUI 和五模块后端未运行。
认证因此失败，不能将已构建包称为业务验收完成。

原 ZIP id `12630401590`，78,859,779 bytes，SHA256
`0cc2e22789ba41924f69caf5060ec47d6bf6809fdbec315a5f997de353a517d9`，
到期 `2027-01-24T05:45:18Z`；Actions 内下载实测与 API digest/size 一致。
本轮 compact 程序 SHA256 `7742a3b339863729ba20281200fb45a5ecd551ce51aab1c98b6ba540516979f6`；
noncompact `09d7f28dca5f276a956f8c40a478e7325c0ebf729a5a26984e18fdd8a83fed90`。
它们只属于本轮，不能替代后续 source 的结果。

新第 2 轮准备：修正搜索基础夹具路径并先生成导航基础夹具；修正父目录定义的后端 target 路径；
补原 drop backend 与真实拖放/粘贴 UI（此前 compact45 的粘贴条目不能覆盖完整业务）。
各独立 GUI 套件即使前一套件失败仍执行，保留失败退出码；身份校验必须包含 drop UI/backend。
### 新第 2 轮（已完成，失败）

source `594ade6c131e575b41d74ecea9706d3b37674645`；run `40276509629` / attempt `1`。
源码 guard、SDK 与全部模块安装、两种真实宿主构建打包及 desktop ctest 4/4 通过。
五模块 owner probe 114 个断言通过，原 drop backend 通过；compact45、G13 十项、
search30、records30、batch27、drop20 的已记录断言均通过。
G13 `shelf_tab_stops_named` 两圈均读到 `Import sources`，但旧失败为何变空名仍未被证明。

保留两项失败：

1. 五模块 UI 前七项通过；原件导出在 SELECT_FOLDER 目录选择器未关闭超时，
   未完成导出、历史和同步三项真实 UI 验收。后端对三者的通过不替代真实 UI。
2. 原 navigation UI 在读取 `surrogate.cfi` 时 FileNotFoundError。
   原 `reader-gtk-navigation-backend` 会生成 normal/surrogate/collapsed 三份 CFI，
   继承 workflow 未执行它；此失败不能记为完整目录业务通过。

整轮 gtk 与 authenticate 均 failure；身份认证正确拒绝 wave3_tools scope 未通过。
原 ZIP id `12630799738`，99,247,221 bytes，SHA256
`864220410ba20c421f9d5e73557259c6be491a4f42f3e32bc8890be7e72981e8`，
到期 `2027-01-24T05:51:32Z`；Actions 内下载实测与 API digest/size 一致。
本轮 compact 程序 SHA256 `7742a3b339863729ba20281200fb45a5ecd551ce51aab1c98b6ba540516979f6`；
noncompact `09d7f28dca5f276a956f8c40a478e7325c0ebf729a5a26984e18fdd8a83fed90`。

当前两文件待验修复：导出选择器采用原 batch driver 的原生目录表格选择流程，
保留最终目录/字节断言；workflow 在导航 UI 前执行原 backend 生成三份真实 CFI。
已向协调者列出两处根因和具体 diff，请求追加一次完整验收后封存；尚未自行启动第三轮。
协调者已审阅两文件完整 diff，并明确批准提交修复与 ledger，追加完整第 3 轮后封存。
导出目录与已通过 batch 驱动夹具都在同一 runner workspace/build 下；batch 的 Path.home 相对遍历已实际通过，导出仍使用产品真实目录，不为驱动移动路径。

### 经协调者授权的新第 3 轮（已完成，失败；封存）

source `4561ef738e073058c900b176062c2d95ae7c5a19`；run `40279255603` / attempt `1`。

| 本轮范围 | 实际结果 |
| --- | --- |
| 自有路径与冻结 guard | 通过 |
| SDK、全部模块、两种 GTK 宿主构建与打包 | 通过 |
| desktop ctest | 4/4 通过 |
| 五模块 owner probe | 114 个断言通过 |
| 原 navigation backend、CFI 生成、drop backend | 通过 |
| 原 compact45、G13 十项 | 通过 |
| 原 search、navigation、reading records | 30、29、30 项通过 |
| 原 batch、drop UI | 27、20 项通过 |
| 五模块真实 UI | 前七项通过，导出目录定位失败；后续三项未完成 |
| authenticate | failure，正确拒绝 wave3_tools 未通过 |

前七项包括原生 More 入口、简洁主界面、整文件标注预览/明确确认/坏文件拒绝，
以及真实字体 lease、坏字体后原 book/part/page/start/end/frame_generation 完全不变且实际 Next/Previous 可用。

剩余阻断已定位到本队 UI 驱动，而非一次导出 owner 返回失败：
`tests/reader_wave3_c10/check_ui.py:152` 在 `chooser` 调用 `click_node(row)`，
`:97` 取得的原生目录表行中心坐标含 `x=-2147483313`；xdotool 报
`mousemove: unrecognized option '-2147483313'` 并退出。
驱动只检查了宽高为正，未确保原生表行已滚动到可点击视口；目录选择器仍开着，
产品尚未取得所选目录并发出 export 命令。因此不能把 backend 导出通过算作真实 UI 导出通过。
后续应先让目标原生表行进入视口，并核对当前目录/选中路径与有效屏幕坐标，
然后维持原有目标目录和逐字节导出断言。不能只加 xdotool `--` 或夹紧坐标代替真实选择。
本阶段按协调者指令封存，不再提交未验代码或新增轮次。

导航缺失 CFI 的接线修复已由本轮真实 backend 与原 UI 29 项通过确认。
G13 本轮两圈 Import sources 均有名，十项通过；旧 run40237525525 空名的原始根因仍未证明。

### 本轮原始工件与实际程序

[主工件/原 ZIP](https://github.com/NoGod3524/EXReader/actions/runs/40279255603/artifacts/12632725811)：
id `12632725811`，name `reader-wave3-c10-40279255603-1`；
99,314,481 bytes；SHA256 `03f2fef3820c41ba125bfc5eacce8a2af84e9dc5304ec5cd38766f877a2db20c`；
到期 `2027-01-24T06:20:35Z`。Actions 内对原 ZIP 的实际 SHA256/字节数与 API digest/size 比对已通过。
另存原 ZIP 的包装工件 id `12632625994`；其内 `c10-original.zip` 是上述原 ZIP，包装 ZIP 自身的 digest 不应混用。
身份报告 id `12632755840` 的 verified=false，原因是五模块 UI scope 未通过。

| 本轮文件 | SHA256 |
| --- | --- |
| `c10-compact-package/EXReader-Linux/bin/exreader-linux` | `7742a3b339863729ba20281200fb45a5ecd551ce51aab1c98b6ba540516979f6` |
| `c10-package/EXReader-Linux/bin/exreader-linux` | `09d7f28dca5f276a956f8c40a478e7325c0ebf729a5a26984e18fdd8a83fed90` |
| `c10-desktop/reader-gtk-drop-backend` | `bc8885df4e805cd218d5db13862e18f08e942a03d79ccbddf6228fc64204243d` |
| `c10-desktop/reader-gtk-drop-native-source` | `084b2a30e04322d35e4ba9c6ad4f24f3e2f4a09a494c0f1604d77096b125fa15` |

推荐检查 compact 包；实际启动用 `c10-compact-package/EXReader-Linux.tar.gz`，
它保留 Linux 执行权限。解压到空目录后执行 `./bin/exreader-linux`。
两种包的 `build.json` 和 `runtime-dependencies.txt` 均在工件中；包已在 Ubuntu 22.04 Actions 原生 GTK/X11 环境启动并执行上述业务。
源码分支为 `codex/team24-gtk`；本机未下载、解包或解析工件。

### 最小接入 diff 与边界

基于 `05c8494eb8320c22b9e7b439cca82e21bc36a461`，三个源码提交依次为
`a34fb18660244e0e6db121035b1ae99193b0b297`、
`594ade6c131e575b41d74ecea9706d3b37674645`、
`4561ef738e073058c900b176062c2d95ae7c5a19`。
自有 diff 共 13 个文件：Linux reader/reading 入口与两个 Wave3 include、GTK owner CMake include、
本队 workflow、四个 C10 测试文件和两份本队文档；公共 desktop/CMakeLists、SDK、原测试和其他平台不改。

业务修复：字体失败先销毁借用 pager 再释放 lease；标注 preview/confirm 使用同一私有快照并显式 discard；
sync 窗口文本自赋值 UAF 与过期 busy 清理；两种布局共用原生低频菜单。
本阶段只建议作为带已知验收阻断的候选接入，不应标记 GTK 五模块验收完成或六平台产品完成。

未覆盖：原 1710/CPU 整体重新验收、完整 G13/Orca/真实读屏、真机、其他五平台、
本轮独立 preferences/page-background/record-compatibility 全套、带真实网络会话的 sync 状态。
当前 history 拒绝跨书跳转；annotation 导入沿用模块 heads-only 合同，不恢复缺失祖先。
本阶段未运行任何本地构建、测试、语法检查、夹具、benchmark、截图或工件操作。
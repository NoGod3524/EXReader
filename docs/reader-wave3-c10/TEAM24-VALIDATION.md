# GTK team24 验收记录

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

尚待父代理登记 source、run/attempt、各 job 真实结论、原 ZIP 身份、实际程序身份、失败与未测范围。

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

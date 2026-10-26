# C09 / Team24 Windows 交付记录

状态：原生代码与公开 codec 已接入，五功能完整验收尚未通过。最后一轮停在系统保存窗口的驱动识别；其后已按实际控件结构修复源码，尚未复验。

## 源码与轮次

- 分支：`codex/team24-windows`。
- 本队固定起点：`310b4223a3d119555f1d04384af7f5b16b7b582f`。
- 最新受测源码：`08e1edf7ee37770c7ce210ab85a2ed4a122045f2`。
- 最后组合轮：[40350379758 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40350379758)，整体 failure；guard success、windows failure、authenticate success。
- 受测后驱动修复：`683d5524575fd00b3e5e4d447e730fb3ba76fd75`，仅新增 7 行 DirectUI 文件名控件识别，`[skip ci]`，未复验。
- 初始两轮预算之外，协调者明确授权了上述一次组合轮。没有自行追加运行。

原失败 `40246233974/1`、`40273584160/1`、`40274692199/1`、本队首轮失败 `40276275043/1` 均保留。`40277257970/1` 在协调者要求等待公开接口时取消，Windows 构建 cancelled、缺包认证 failure，未作完整成功结果使用。完整列表见 `docs/reader-wave3-c09/team24.md`。

## 最后同轮实际结果

- 已通过：精确自有范围与依赖 blob guard、SDK/产品/模块构建、公开 codec 的真实 Windows 宿主链接、打包原 26、原 compact22（22/22）、原 raw owner suite/fresh、ZIP 解压后逐文件身份、解压程序原 26。
- 五功能 UI 实际通过 2 项：原生菜单入口；实际划线定位后的历史后退/前进。未以此推断其余 14 项通过。
- 停止点：`tests/reader_wave3_c09/check_ui.py` 的标注导出系统保存窗口。真实诊断显示文件名为 `Edit`、ID `1001`、父 `ComboBox`、祖父 `FloatNotifySink`；旧驱动仅接受 ID `1152/1148`。地址栏的 ID `1001` 是 `ToolbarWindow32`，可以按类型和父链区分。最新修复保留等待、唯一性与业务断言，未用坐标。
- 标注导出/预览/确认导入、字体失败旧 frame/lease/重启、原件逐项导出、已有 FAILED 会话的只读同步队列等完整操作在最后一轮没有到达，仍未验收。
- 真机、读屏、完整 1710 与 CPU 预算未在此 Windows 宿主轮次重跑或据此授予通过；原文件与预算未放宽。这是六平台阅读器中的 Windows 主线。

## 原 ZIP 与实际程序

同 run、同 attempt 的 [原始工件 12663945607](https://github.com/NoGod3524/EXReader/actions/runs/40350379758/artifacts/12663945607)：

- 名称：`c09-windows-wave3-40350379758-1`。
- 工件归档：19,105,651 bytes；digest `sha256:c528306681a1f0fc6352b3b860501e8a39e6394b4970c1ea80e69b36d50cf9c6`。
- 有效期：`2027-01-24T15:32:49Z`。
- 内部原交付包 `EXReader-wave3-windows.zip`：17,500,770 bytes；SHA-256 `8f245e154df69fc5218307bea76de214e1bcfe0ecb96f4c10a5bcc823be163f4`。
- 实际 `EXReader/EXReader.exe`：SHA-256 `dc2671bf103abc22008110c9b1efb3ec3aa75582f0c30004d122ca100d549b3b`。
- 认证 `verified=true` 只确认上述身份；受测 Windows 报告 `accepted=false`。

所有构建、测试、夹具、截图、下载、解压、解析和身份核对均在 Actions。这里的身份来自该轮认证日志；本地没有下载或解析工件。工件保留 compact22、解压 UI 失败截图、日志、map、报告与内层 ZIP。

启动形态：解压内层 ZIP 后运行 `EXReader/EXReader.exe`；实际 GUI 驱动使用同目录 `Reader.otf` 与独立 `--data` 目录，原 26 自检也由解压后的 EXE 执行。默认无参数双击路径未单独验收。

## 公开依赖准入

核心生产提交：`a911cd0e8405a362dae1bb489190de02c4c81d51`，精确集成为本队提交 `08e1edf7`；仅包含 reading-state 的新候选头、CMake opt-in 和条件公共 C wrapper 三文件。独立 installed 准入：[40348964690 / 1](https://github.com/NoGod3524/EXReader/actions/runs/40348964690)，受测源码 `347165fe601f1bdb0cd3bb1da4c672f696195a4e`，Linux/Windows/macOS 的 C/C++ consumers 与身份汇总均 success。此结果单列为依赖准入。

`team24_guard.py` 只允许三个固定依赖 blob；原 `guard.py` 未改。旧公共头、原 0.1/0.2 行为、SDK/导出/公共 CMake/旧判定器未改。Windows 删除手写私有 extern 与 wrapper，包含 installed 新头，保留实际 anchor version 2；构建要求显式 raw 与 pure-capture capability。

## 最小合入范围与继续点

相对于本队起点，生产修复集中在 `examples/reader.c` 与四个 `windows_*` 文件：接受 frame 后、保存 worker 前提交历史；字体旧 lease 在新 worker 前释放；线程启动失败恢复 owner；原件结果保留 book ID；Markdown 覆盖确认；More 关闭可见；同步队列/冲突未知分开；现存 SQLite 产品身份不符则只读失败；公开 codec 接线。

另含本队测试、工作流、文档，以及明确批准的三个 core 依赖文件。整个聚合增量可从 `git diff 310b4223 683d5524` 审阅。保留既有焦点、selection、NULL、工作区实现，不重写原 host。

继续时使用 `683d5524` 的文件名控件识别修复，先保留最后失败与原包；下一次完整运行需要协调者另外授权。入口仍为 `.github/workflows/reader-team24-windows.yml`，不得把未复验源码或两个通过 UI 项写成五模块完成。

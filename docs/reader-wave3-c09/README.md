# C09 — Windows 五模块原生接入

固定起点 `d263ce5228838ac90c0a0dc13a5193d4a7739681`（候选，不是已验收 BASE）。分支 `codex/reader-wave3-c09`。

## 入口（均为原生菜单项 / 原生对话框，默认书架与阅读页不增加任何控件）

| 功能 | 菜单 | 窗口 / 控件 |
| --- | --- | --- |
| 标注导入/导出 | 阅读 → 标注导入与导出… | 导出（系统保存窗口，JSONL+Markdown，原子发布）；导入先“预览导入文件…”（只读，列出新增/重复/冲突/缺父/恢复受阻、位置“找到/未找到/NULL保留/未核对”和指纹），预览通过后“确认导入”再弹确认框，才逐项提交；取消保留已提交项 |
| 字体库 | 阅读 → 字体库… | 导入本地字体（失败不动字体库与画面）、选择、恢复内置、删除；选择的字体写入 `<data>\wave3-font.txt`，重启恢复 |
| 导出原件 | 书库 → 导出原件… | 多选书架中的书 → 系统目录选择器（取消则不创建文件）→ 逐项结果（已导出/已存在·内容一致/拒绝/失败）和实际路径 |
| 跳转历史 | 阅读 → 后退 / 前进（Ctrl+[ / Ctrl+]） | 每次真实落点（打开、翻页、搜索/目录/记录跳转）记录；后退/前进在独立原书里取得公共 FOUND 并实际定位后才移动游标；失败/取消/另一本书则游标不动 |
| 同步状态 | 书库 → 同步状态… | 只读：状态未知、待处理、冲突分行显示；无任何写入/重试/确认控件 |

## 接入方式

- 唯一的共享 CMake 入口 `apps/reader/desktop/windows_feature_integration.cmake`（`-DEXR_READER_WINDOWS_WAVE3=ON`），生成额外目标 `EXReaderWave3`；公共 `apps/reader/desktop/CMakeLists.txt` 未改。
- 源码：`examples/reader.c` 的 `EXR_READER_WINDOWS_WAVE3` 小钩子（job 类型、完成回调、菜单/快捷键/关闭）+ `apps/reader/desktop/windows_wave3.inc`（全部逻辑）+ `windows_wave3_types.h` + `windows_wave3_bridge.cpp`（仅把 reading-state 的 C++ 链接 raw 编码器暴露给 C）。菜单项在 `windows_compact_ui.inc` 的既有“书库/阅读”子菜单中追加，顶层菜单数与原有命令 id 不变。
- 线程：字体库与跳转历史是 owner 线程绑定，全部在 UI 线程；标注预览/提交/导出、原件导出、历史定位在 host 唯一的串行 SDK worker（`JOB_WAVE3`），持 `g.library_lock` 的 SDK 访问与既有 records 路径一致。不新增 SDK、store、解析器、WebView。
- 字体切换：新字体 lease 打开 → 用同一 `JOB_OPEN` 候选 session 重排；成功时旧 session/pager 先被替换，之后才释放旧 lease；失败/取消时先释放候选 session/pager，再释放新 lease，旧画面不动。

## 测试与打包

- `tests/reader_wave3_c09/guard.py`：固定 seed、自有路径范围、公共 CMake 与冻结文件未改。
- `tests/reader_wave3_c09/build.py`：构建 SDK3.41、product、raw 全家族 + 6 个新模块 → `EXReaderWave3` → `tools/build_windows_host.py` 打包 → 保留的原 compact22 检查、原 raw owner suite/fresh、新增端到端 UI 测试 → ZIP 往返。
- `tests/reader_wave3_c09/check_ui.py`：真实菜单 id、系统文件/目录窗口、确认框、对话框按钮的端到端驱动。
- `.github/workflows/reader-wave3-c09.yml`：guard → windows → authenticate（run/attempt/ZIP/EXE/artifact 身份绑定）。

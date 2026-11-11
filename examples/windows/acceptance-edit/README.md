# X3 验收记录 · 2026-11-10

Y3 后续补录见 [真实窗口证据与限制](../../../docs/ui/evidence/edit-shell/README.md)：
已取得拖选反白、脏标题与原生关闭弹窗，修复 Tab 写入正文和编辑区缺少焦点提示；
微软拼音、可见光标与焦点环仍未通过，不能视为 X3 全项验收完成。
下文保留 X3 当次原始记录。

实现和证据均位于 `examples/windows/`；入口接线位于 `examples/reader.c`。
未修改 `src/`。本机测试使用 `.build-sdk` 中带 #119 与 X1 DOCX 双向桥的 SDK、
GNU 16.2.0、Release 构建。

| 验收项目 | 结果 | 证据 |
|---|---|---|
| 连续输入 10 字符，一次撤销全部消失 | 通过 | `check_shell_edit_ui.log`，生产 `WM_CHAR` / `WM_KEYDOWN` 处理函数 |
| 中文「你好世界」作为一个结果一次插入/撤销 | 模型级通过；微软拼音实测待补 | `check_shell_edit_model.c`，12 字节 UTF-8，一次事务 |
| 撤销 20 次 / 重做 20 次 | 通过；前后字节与哈希一致 | `ui-undo-*.utf8` / `ui-redo-*.utf8` |
| DOCX 保存后关闭模型并重开 | 通过；25 字节内容逐字节一致 | `roundtrip.docx`、`ui-before-save.utf8`、`ui-after-reopen.utf8` |
| 退出测试进程后，用新进程重开 DOCX | 通过；25 字节内容与保存前一致 | `fresh-process-reopen.log`、`process-after-reopen.utf8` |
| 关闭未保存时保存 / 放弃 / 取消 | 隔离 HWND 测试通过；真实窗口截图待补 | `check_shell_edit_ui.log`；原生三按钮对话框 |
| 锁住目标文件导致保存失败 | 通过；原文件内容保留，脏标记保留 | `check_shell_edit_ui.log` |
| DPI / 缩放几何 | 通过；96 DPI/100% → 144 DPI/200%，行高比 3.0 | DirectWrite 布局与命中测试 |
| 光标 / 选区 / IME 候选窗真实截图 | 待补 | 本次 Computer Use 被用户按物理 Esc 停止，之后未继续操作界面 |
| `-Wall -Wextra -Werror` 零警告 | 通过 | `build.log`，完整重编译 |

自动化命令：

```powershell
python examples/windows/check_shell_edit.py --build examples/windows/.build-verify --output examples/windows/acceptance-edit --clean-first
```

完整数字见 [report.json](report.json)。主要 SHA-256：

| 内容 | SHA-256（前后相同） |
|---|---|
| HWND 撤销前基线 / 20 次撤销后 | `393cb862d18809a79850af1dc946c400f3cdb74e3f767edf3bc178d3aab2c3df` |
| HWND 重做前 / 20 次重做后 | `5ccd0688f0515a3333bda893fd79e748a747601e20dde6db3c3ef778d79eb2a4` |
| 保存前 / 重开后文本 | `393cb862d18809a79850af1dc946c400f3cdb74e3f767edf3bc178d3aab2c3df` |
| `roundtrip.docx` 文件 | `393abecaf7d7ff84d9b907ef832d918f5d3168213a57ea3ed72d7410f05f6973` |

DOCX ZIP 时间戳随重跑变化，以当次 `report.json` 为准。

当前 SDK 的文本替换由插入/删除段落组成。涉及段落会重建，已建模的段落与 run 属性、
不透明内联字节会复用；未建模的段落 XML 模板不会保留。完整延续此类格式需要引擎提供
原位文本修改命令。分节继承已有独立回归检查。

真实窗口验收仍需：打开 `window.txt`，用 Ctrl+E 开启编辑；捕获竖线光标和拖选反白；
切到微软拼音，输入 `nihaoshijie`，在上屏前捕获带下划线的预编辑和光标旁的候选窗；
一次上屏「你好世界」，确认一次 Ctrl+Z 全部撤销；修改后关闭并捕获保存提示。
截取完整的真实窗口，并记录窗口 DPI 与缩放。

首次启动本机默认字体链曾超过 SDK 的 128 MiB 上限。隔离验证使用显式字体可启动：

```powershell
examples/windows/.build-verify/EXReader.exe --data examples/windows/.build-verify/manual-profile --font C:/Windows/Fonts/arial.ttf
```


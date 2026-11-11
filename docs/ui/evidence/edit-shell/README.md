# Y3 · X3 真实窗口验收补录 · 2026-11-10

**本轮未达到全项验收。** 已取得真实拖选反白、脏标题和关闭提示；修复 Tab 写入正文及编辑区缺少焦点提示的问题。微软拼音组合、候选窗、真实中文上屏后 Ctrl+Z、可见光标和焦点环仍未通过。下面保留失败现场与替代证据，不把后台消息测试算作微软拼音实测通过。

分支：`codex/dx-shell-edit-20261110`。功能改动仅在 `examples/windows/`，未修改 `src/`。未调用 Computer Use、浏览器自动化、Tinysky、SendInput 或 keybd_event；未使用 mockup、手绘、拼接或补画。

## 真实窗口原图及 DPI

图像全部由仓库 `ops/capture_window.py` 的 DPI 感知 `PrintWindow(..., 2)` 直接写出。每张同名 JSON 保留窗口/客户区尺寸、屏幕坐标、`GetDpiForWindow`、实际线程焦点和前台 HWND。DPI 缩放为 `120 / 96 = 1.25`，即 125%。分辨率均指 PNG 物理像素。

| 请求 | 原图 | 分辨率 | DPI / 缩放 | 结果 |
|---|---|---|---|---|
| 1. 可见插入光标 | [01-caret-attempt.png](01-caret-attempt.png) | 1180 × 900 | 120 / 125% | 未通过：编辑模式真实窗口，未捕获可见光标 |
| 2. 拖选反白 | [02-selection.png](02-selection.png) | 1180 × 900 | 120 / 125% | 通过：PostMessage 鼠标按下、逐段移动、抬起；第二行反白 |
| 3. 拼音候选窗与组合下划线 | [03-ime-attempt.png](03-ime-attempt.png) | 1180 × 900 | 120 / 125% | 未通过：实际得到正文 `nihaoshijie`，没有组合下划线或候选窗 |
| 4a. 未保存标题 | [04-unsaved-title.png](04-unsaved-title.png) | 1180 × 900 | 120 / 125% | 通过：标题 `* fixture.txt — EXReader [编辑]`，宿主已被模态对话框禁用 |
| 4b. 未保存关闭提示 | [04-unsaved-dialog.png](04-unsaved-dialog.png) | 382 × 220 | 120 / 125% | 通过：原生“保存更改”对话框、Yes / No / Cancel |
| 焦点环 | [05-focus-attempt.png](05-focus-attempt.png) | 1180 × 900 | 120 / 125% | 未通过：已清除隐藏焦点提示状态，但编辑区没有实际焦点 |

主窗口和模态对话框分别是 HWND，PrintWindow 主窗口不会把独立弹窗一起捕获，因此 4a、4b 分别保存原始图像；未合成一张。主窗口使用宿主内置 `--offscreen`，位置为 `(-32000, -32000)`，是实际创建并绘制的生产 HWND。弹窗由 Windows 放在 `(772, 492)`。

## 微软拼音三点结论

本机 zh-Hans-CN 的已配置输入法确认为 Microsoft Pinyin，TIP 为 `{81D4E9C9-1D3B-41BC-9E6C-4B40BF79E35E}`，profile 为 `{FA550B04-5AD7-411F-A5AC-CA038EC515D7}`；见 [input-methods.txt](input-methods.txt)。向测试宿主投递 `WM_INPUTLANGCHANGEREQUEST`，目标线程 HKL 为 `0x8040804`；对其 Default IME 发送 `WM_IME_CONTROL / IMC_SETOPENSTATUS` 后，查询 open 状态从 0 变为 1；见 [ime-open-attempt.json](ime-open-attempt.json)。随后逐键投递 `nihaoshijie` 的 `WM_KEYDOWN/UP`，没有直接发送中文 `WM_CHAR`，也没有合成 `WM_IME_COMPOSITION`。

1. **组合下划线及文档不写入：做不到，因为允许的后台逐键路径没有触发组合期，字母直接写入正文；**[03 原图](03-ime-attempt.png)与[上屏尝试后的实际文件](real-ime-attempt-after.utf8)证明该尝试未通过；替代证据是 HWND 回归中预编辑 display 与 model 分离的断言。
2. **候选窗靠近光标：做不到，因为本次没有生成候选窗，无法测量其位置；**[03 的窗口与焦点记录](03-ime-attempt.json)显示编辑区 HWND 为 `14683206`，线程实际 focus 却为顶层 `462704`、caret 为 null；替代证据是 HWND 回归对 `IMR_QUERYCHARPOSITION` 的屏幕位置、行高和越界查询断言。
3. **「你好世界」一次上屏、一次 Ctrl+Z 全部消失：真实微软拼音路径做不到，因为没有取得中文结果；**[实际三段文件](real-ime-attempt-before.utf8)只支持“字母输入后一个撤销菜单命令恢复”，中文模型事务及隔离 HWND 的 Ctrl+Z 结果另列如下，不能代替真实 IME 验收。

本轮没有足够证据判定“候选窗必须真实前台焦点”是唯一原因；已观察到的限制是编辑区没有实际焦点，PostMessage 输入没有进入本次微软拼音组合路径。

## 撤销粒度：实际文本与替代测试

真实后台逐键尝试的输入前、投递后、一次 `EDIT_UNDO` 菜单命令后分别为以下内容（均以 LF 结尾）：

```text
输入前：
X3 host editing
Select this line, then type here.

逐键 nihaoshijie 后：
nihaoshijieX3 host editing
Select this line, then type here.

一次撤销菜单命令后：
X3 host editing
Select this line, then type here.
```

对应 [before](real-ime-attempt-before.utf8)、[after](real-ime-attempt-after.utf8)、[one-undo-command](real-ime-attempt-one-undo-command.utf8)。这不是中文上屏，也不是物理 Ctrl+Z；PostMessage 投递修饰键不保证目标 `GetKeyState` 的 Ctrl 状态，所以未把菜单命令冒充快捷键。

替代证据保留完整三段字节：

| 测试层 | 输入前 | 输入后 | 一次撤销后 |
|---|---|---|---|
| 中文单结果模型事务 | [空文本](automated/cjk-model-before.utf8) | [你好世界](automated/cjk-model-result.utf8) | [空文本](automated/cjk-model-one-undo.utf8) |
| 隔离 HWND：连续中文 WM_CHAR，再走生产 Ctrl+Z 处理 | [空文本](automated/cjk-hwnd-before.utf8) | [你好世界](automated/cjk-hwnd-wmchar.utf8) | [空文本](automated/cjk-hwnd-one-ctrl-z.utf8) |

第二行复用原有测试的线程内 `SetKeyboardState` 保存/恢复机制，再通过 `WM_KEYDOWN` 调用生产处理函数；不操作其他进程或真实键盘。它验证 HWND 输入与撤销处理，未验证微软拼音 `GCS_RESULTSTR`。

## 键盘与焦点

真实 HWND 投递了 Left / Right / Up / Down、Home / End、Backspace / Delete。每步保存到隔离的 fixture，逐字内容和线程状态见 [keyboard-results.json](keyboard-results.json) 与 `keys-*.utf8`。Backspace 后首行为 `X3 host editin`；紧接着 Delete 删除换行，得到 `X3 host editinSelect this line, then type here.`。生产处理函数的回归还断言 Home=0、Right=1、Left=0、End=10，并核对删除后的精确字节，避免仅凭文本未变化判定导航通过。

Tab 修复前确实替换选区并插入制表符，见 [tab-before-fix.png](tab-before-fix.png)。原因是 `shell_edit_translate` 把编辑区所有按键直接分发，且 `WM_GETDLGCODE` 请求 `DLGC_WANTTAB`。修复后普通 Tab / Shift+Tab 交还现有 `IsDialogMessage`，不再声明 WANTTAB；回归断言路由与正文不变。编辑区绘制补上与阅读视图一致、遵守 `UISF_HIDEFOCUS` 的原生焦点矩形。

**Tab 在按钮与编辑区实际移动、光标可见帧及焦点环截图做不到，因为本轮后台窗口的实际焦点一直未进入编辑区。**[tab-after-fix-state.json](tab-after-fix-state.json)、[01 状态](01-caret-attempt.json)、[05 状态](05-focus-attempt.json)保留现场。未通过合成 `WM_SETFOCUS`、假定焦点或强制绘制来制造截图。替代证据为上述路由回归与绘制条件；可见状态仍待验收。

## 复跑与范围

```powershell
python -X utf8 examples/windows/check_shell_edit.py --build examples/windows/.build-verify --output docs/ui/evidence/edit-shell/automated
python -X utf8 ops/send_keys.py <PID> --inspect
python -X utf8 ops/send_keys.py <PID> --hwnd <PAGE_HWND> --drag 50 85 265 85
python -X utf8 ops/send_keys.py <PID> --hwnd <PAGE_HWND> --letters nihaoshijie
python -X utf8 ops/capture_window.py <PID> shot.png --hwnd <HWND>
```

测试窗口使用独立 `--data` profile 与 Arial 字体，未使用现有用户书库；profile 不提交。`ops/send_keys.py` 检查 HWND 所属 PID，键盘和鼠标仅 PostMessage；`--set-text` 使用 Windows 可跨进程封送的 WM_SETTEXT，供原生文件对话框使用。`capture_window.py` 增加可选的 PID 校验 HWND，解决同一进程有主窗口和弹窗时原先只能唯一匹配一个窗口的问题。

**启动异常记录：**首次尝试 `SW_SHOWNOACTIVATE` 仍被宿主取得前台焦点，前台 HWND 从 `5443024` 变成 `2231522`；已向该测试实例投递关闭消息退出。见 [session.json](session.json)。后续改用自带 `--offscreen / WS_EX_NOACTIVATE`；所有交付图像均来自后续后台实例，见 `session-offscreen.json`、`session-fixed.json` 和每张图片的状态记录。测试实例已关闭，原先就存在的 EXReader 进程未关闭。

自动检查、构建零警告、DOCX 保存重开、20 次撤销/重做和锁文件保护结果见 [automated/report.json](automated/report.json)。完整日志以 `.txt` 后缀保留，截图尺寸与 SHA-256 见 [manifest.json](manifest.json)。这份补录保留所有未通过项，X3 的真实微软拼音验收仍为待完成。

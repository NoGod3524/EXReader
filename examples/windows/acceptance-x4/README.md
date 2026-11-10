X4 自动保存、脏标记与崩溃恢复，6 项验收全部通过。实测日期：2026-11-10，Windows / gcc (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r1) 16.2.0。

改动仅在 `examples/windows/*` 与 `examples/reader.c`；`src/` 没有改动。笔记和高亮作为每本书的一个 JSON 文档保存；自动保存写到该 JSON 路径加 `.autosave`。默认间隔 30 秒，`--autosave-seconds N` 可配 1–86400 秒。

| 验收 | 实测结果 | 证据 |
| --- | --- | --- |
| 1. 自动保存 | 编辑后执行 `probe_wait\|35000`；检查点检测到新副本；原文件字节和修改时间均未变化 | [驱动日志](writer/drive.log)、[副本载荷](writer/autosave-payload.json)、[带 CRC 头的副本](writer/autosave-container.bin) |
| 2. 强杀后重启 | 对真实宿主 PID 12264 执行 `Stop-Process -Force`；启动重开上一本书时提示恢复；恢复后 dirty=1，显式保存后 dirty=0；内容 SHA-256 与强杀前一致 | [恢复日志](restart/drive.log)、[恢复状态](restart/recovered.annotations.json)、[恢复后保存的原始字节](restart/recovered-saved.json) |
| 3. 保存中强杀 3 次 | 生产 `shell_save_replace` 在专用检查进程的 3 个写入阶段被强杀；三次原文件均为上一完整版本，52 字节 | 下表及 [机器结果](results.json) |
| 4. 副本损坏 | 手动截断至 13 字节，明确报“副本损坏，无法恢复”；原文件不变，宿主正常退出，退出码 0 | [截断副本](truncated.autosave)、[错误状态](corrupt/rejected.annotations.json)、[日志](corrupt/drive.log) |
| 5. 脏标记 | 连续 编辑→保存→再编辑，dirty=1→0→1，标题栏 `*`→无 `*`→`*`；关闭选择取消保持窗口及修改，选择保存后关闭 | [编辑截图](titles/edit-1.png)、[保存截图](titles/save-2.png)、[再编辑截图](titles/edit-3.png)、[关闭日志](titles/drive.log) |
| 6. 编译 | C / C++ 均启用 `-Wall -Wextra -Werror`，0 warning | [构建日志](build.log)、[最终构建日志](build-final.log)、[实际编译命令](build-commands.txt)、[构建与源码哈希](build.json) |

自动保存的原文件修改时间为 `2026-11-10T20:13:47.775807+00:00`，副本修改时间为 `2026-11-10T20:14:17.798783+00:00`。脚本等待 35000 ms；父进程从观察到编辑检查点到观察到等待结束的间隔为 34.938 秒。

| 内容 | SHA-256 |
| --- | --- |
| 保存前的原文件 | `93d9548c6b601337425fde1657baec2ee8a369e4448e5074591104f9e21ef474` |
| 强杀前的自动保存载荷 | `8fa8fe75929eaf6d8997d16b368683d8275c9527498a00807e4db794df27b977` |
| 重启恢复后显式保存的内容 | `8fa8fe75929eaf6d8997d16b368683d8275c9527498a00807e4db794df27b977` |
| 包含 24 字节 CRC / 长度头的完整副本 | `97ccd95e3aa62466250d2ccb1d70efc5def65e021ad5c6ddb0eed857ea576080` |

副本载荷包含未点击保存的 `unsaved draft 中文 😀 before force kill`。机器结果及原始载荷均已归档，可直接重算哈希。

| 次数 | 强杀阶段 | PID | 临时文件字节数 | 原文件字节数 | 强杀后原文件 SHA-256 |
| --- | --- | --- | --- | --- | --- |
| 1 | `writing` | 32096 | 65536 | 52 | `5bddd86e73b1f8c371d862bf4f9ee8b76aaeae2eb56116fc8ea9582ba5fdfba3` |
| 2 | `flushed` | 31140 | 1048575 | 52 | `5bddd86e73b1f8c371d862bf4f9ee8b76aaeae2eb56116fc8ea9582ba5fdfba3` |
| 3 | `before-replace` | 30740 | 1048575 | 52 | `5bddd86e73b1f8c371d862bf4f9ee8b76aaeae2eb56116fc8ea9582ba5fdfba3` |

三次强杀均由脚本调用 PowerShell `Stop-Process -Force`；目标检查进程直接包含与宿主相同的 `shell_save.h`。写到第一个 65536 字节块、临时文件 Flush 完成、替换之前分别暂停。暂停钩子只编译进 `check_shell_save.exe`。三份强杀后原文件已存于 [storage](storage)。

另外通过：启动恢复选“否”会删除副本、保持 dirty=0 且原文件不变；关闭的 Save / Discard / Cancel；1 秒配置；相同脏版本不重复写副本；回读损坏时恢复原内容与修改时间；回滚再次失败时保留 `.bak`；新文件首次保存失败后撤销；未提交多行笔记草稿；取消草稿；切书间隙阻止编辑；切换固定页文档时释放旧笔记状态。[存储自检结果](results.json)、[笔记生产路径测试](annotations.log)。

还通过 computer-use 对一份独立测试配置检查了真实可见的启动弹窗：[恢复提示截图](recovery-prompt.png)、[弹窗文本](recovery-prompt.txt)。选“是”后笔记正文为 `unsaved draft 中文 😀 before force kill`，标题带 `*`；Ctrl+S 后标题清除 `*`、副本删除，原文件哈希与载荷一致：[保存截图](ui-saved.png)、[独立 UI 检查哈希](ui-recovery.json)。

复跑时使用空的输出目录，SDK 开启 `EXR_ENABLE_PDF=ON`：

```powershell
cmake -S examples/windows -B examples/windows/.build-x4-final -DEXR_SDK=C:/path/to/stage -DEXR_READER_WINDOWS_SHELL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build examples/windows/.build-x4-final --target EXReader check_shell_save check_shell_selection --parallel 4
examples/windows/.build-x4-final/check_shell_selection.exe annotations tests/fixtures/fonts/primary.ttf
python -X utf8 examples/windows/check_shell_autosave.py examples/windows/.build-x4-final/EXReader.exe C:/Windows/Fonts/NotoSerifSC-VF.ttf examples/windows/.build-x4-final/check_shell_save.exe examples/windows/.build-x4-final/new-evidence
```

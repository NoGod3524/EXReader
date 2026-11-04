# Windows 包人工验收清单 — 2026-11-04

构建来源：main `4efd33666640e8bd8409e15c432767572894226c`；Windows 单作业 run `41909199114`。交付包 SHA-256、下载链接和文件清单见同目录 `BUILD.md` / `PACKAGE-FILES.txt`。

以下 10 项均待人工执行，不能用 CI 自检结果代填。测试前记录 Windows 版本/构建号、CPU/RAM、显示缩放、包 SHA-256、测试人和时间到 `00-environment.txt`。建议在独立测试账户或 Windows Sandbox 中操作；截图/日志保存在包目录之外。记录每项 PASS / FAIL / 未执行；缺少输入书籍时记“未执行”，不算通过。

| # | 用例与操作 | 怎么算通过 | 怎么记录 |
| --- | --- | --- | --- |
| 1 | 安装：校验 ZIP SHA-256，完整解压到普通用户可写目录（含空格/中文路径），不从 ZIP 内直接启动。 | ZIP 校验一致、解压无错误；EXReader.exe、SDK DLL、Reader.otf、OFL.txt、Sample.epub、README.md、FONT-README.txt 和许可证齐全；无需编译或管理员安装字体。 | `01-install.png` 展示解压目录；`01-install.txt` 记录路径类型、SHA-256 校验和文件清单对照结果。 |
| 2 | 首次启动：在空白测试配置下双击 EXReader.exe。 | 窗口正常显示并响应操作；无缺 DLL/加载器错误、崩溃、死锁或被遮住的错误框。首次运行安全提示单独记下；不以绕过崩溃作为通过。 | `02-first-launch.png`；`02-first-launch.txt` 记录启动耗时、提示原文和退出情况；崩溃时另存 `02-crash-event.txt`（Windows 应用程序事件记录）。 |
| 3 | 打开 EPUB：通过 UI 导入/打开包内 Sample.epub。 | 能打开并显示非空正文；标题/正文可辨识；打开失败有明确错误；关闭再打开同一书仍可读。 | `03-open-epub.png`；`03-open-epub.txt` 记录文件名、SHA-256、首屏首句及错误（若有）。 |
| 4 | 连续翻页 100 次：使用合法且至少有 101 个可翻页视图的 EPUB，从起点执行 100 次“下一页”，中途记录内容标记。 | 100 次操作均完成，无崩溃、卡死、无解释的空白、重复停页或跳过内容；随后回退一页和前进一页能回到相同内容。跨章页码重置不能误判为少翻页。 | `04-page-turns.csv` 每次记序号、时间、章节/页码和首句；截图 `04-page-001.png`、`04-page-025.png`、`04-page-050.png`、`04-page-075.png`、`04-page-101.png`；输入身份写 `04-book.txt`。 |
| 5 | 改字号：在同一段落执行“小 → 大 → 小”，每次等待重排完成。 | 字形大小真实变化；正文无裁切、错序、持续空白；重排后仍定位在同一段落附近；翻页可继续。页数变化本身不算失败。 | `05-font-small.png`、`05-font-large.png`、`05-font-restored.png`；`05-font.txt` 记录设置值和段落原文。 |
| 6 | 重启恢复位置：读到可唯一识别的中段，记下句子，正常退出，再启动并打开同一书。 | 恢复到已读书籍及相同内容位置（以段落/句子核对，不能只看页码）；字号设置保留；无跳回开头或悄悄换书。 | `06-before-restart.png`、`06-after-restart.png`；`06-resume.txt` 记段落原文、操作时间、配置目录；完全退出后备份测试 profile 为 `06-profile.zip`（仅测试数据）。 |
| 7 | 大书：打开一个文件长度严格大于 52,428,800 字节的合法 EPUB，尝试首屏、翻页及定位到后部。 | 成功导入并读出真实正文，能继续翻页/定位；无崩溃、内存耗尽或持续无响应。记录实测耗时/峰值内存，不手填性能结论；明确拒绝大书记为本项 FAIL，不算“有错误提示就通过”。 | `07-large-book.txt` 记录来源/许可、字节数、SHA-256、操作耗时；`07-large-open.png`、`07-large-late.png`、`07-memory.png`；失败记 `07-error.txt`。 |
| 8 | 缺字体：先退出程序，在包副本中把 Reader.otf 改名，再以新测试配置启动并打开书；测试后恢复字体。 | 缺字体被明确报告，或使用可读且明确可识别的回退字体；不崩溃、不静默空白、不持续显示方框；恢复字体后重新启动能读。 | `08-missing-font.png`、`08-font-restored.png`；`08-font.txt` 记录改名、启动参数、错误原文/回退行为；崩溃另存 `08-crash-event.txt`。 |
| 9 | 中文竖排：使用明确声明 writing-mode: vertical-rl 的合法中文 EPUB，含中文标点、引号、数字和中英混排，并与已知参考页面核对。 | 汉字竖排、列从右向左；标点/引号位置与字形方向合理，混排无重叠、丢字或裁切；翻页不改变阅读顺序。静默横排替代不算通过。 | `09-vertical-reference.png`、`09-vertical-actual.png`、`09-vertical-next.png`；`09-vertical.txt` 记录 EPUB 字节数/SHA-256、参考来源及逐项差异。 |
| 10 | 卸载后残留：退出并确认进程结束，备份测试数据，删除解压目录；选择“彻底清理”时同时清理该测试 profile（默认位于 %LOCALAPPDATA%\EXReaderHost，使用 --data 时以实际路径为准）。 | 无残留进程、锁定文件、自启动项、服务或安装字体；包目录已删除。彻底清理后测试 profile 也消失；若主动保留阅读数据，必须列出路径和内容，不能声称“无残留”。不得删真实用户书库或其他程序目录。 | `10-before-cleanup.txt` / `10-after-cleanup.txt` 记录包/profile/进程/自启动/服务/字体对照；`10-cleanup.png`；保留项写 `10-retained-data.txt`，异常写 `10-residue.txt`。 |

结果汇总写 `RESULTS.csv`：`case,status,evidence_files,issue_id,notes`。发现问题只记录复现步骤、期望/实际、截图或事件日志，保持该 Release 二进制不变；不修 bug，也不把未执行记为 PASS。

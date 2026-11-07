# 大封面宿主打开修复 — 2026-11-06

基线：`7b20c5a0`。本地实现及七项验收全部通过；首次打开／恢复／故障注入三项 UI 已按用户批准，以离屏窗口 + PrintWindow 完成。未手动运行 CI、未取消 workflow run。

## 三处修复

- `examples/reader.c:1585`：get-mode 分页缓存仍为 2 页，字节预算从 8 MiB 增为 **32 MiB = 33,554,432 字节**。原图解码资源计入缓存，预算采用固定下限。紅樓夢封面实际计费 **15,372,040 字节**。
- `examples/reader.c:5199`：普通失败分支始终调用 `describe_error(status, error)` 并发布其结果。提前写入的恢复提示不再覆盖真实错误。
- `src/flow.c:564`：分页当前页无正文行、无图片且剩余高度为正时，适配高度取整页高度与 `exr_flow_bottom(f) - f->y` 的较小值。已有正文／图片仍用整页高度并正常换页。

`src/` 变更已在 [R-PROTECTED-TREES.md](../ci-packaging-20261103/R-PROTECTED-TREES.md) 登记。新增 `tests/test_page_cache.c:253` 回归，覆盖仅有前置 margin、已有正文、已有图片三种情况：首图 y=8 / height=120；已有内容后的图换至新页 y=0 / height=128。旧 flow 退出 **1**，修复后退出 **0**，**5,187 checks**。未改夹具或工作流。

## 七项验收进度

| 项目 | 数字与结果 |
|---|---|
| 1. 首次打开进入阅读屏、显示封面 | 离屏 UI **17/17 步通过**；进入阅读屏、part=0、内部 page=0／界面 1:1，封面可见，缓存计费 **15,372,040 字节**；[截图](ui-first/first-cover.png)、[日志](ui-first/DRIVE.txt) |
| 2. 从现有 part=0 / position=0 恢复 | 真实现有记录副本（book_id=2），离屏 UI **16/16 步通过**；显示恢复成功、进入阅读屏、part=0、内部 page=0／界面 1:1，封面可见；[截图](ui-restore/restored-cover.png)、[日志](ui-restore/DRIVE.txt) |
| 3. 拉丁 Sample.epub | **42→42 页，0/42 像素 SHA-256 差异**，固定参数见下 |
| 4. 中文完整遍历 | **1632→1632 页，821108→821108 字形**；固定 720×1040/36/28/1.5/10；status=0 |
| 5. 临时 8 MiB 故障 | 离屏 UI **13/13 步通过**；未进入阅读屏，状态栏显示 `打开书籍失败：超出宿主或SDK限制（Page exceeds the pager cache byte budget）`，无恢复成功提示；无窗口探针确认 **EXR_LIMIT(6)**；[截图](ui-fault/fault.png)、[日志](ui-fault/DRIVE.txt) |
| 6. --self-test | **退出码0、checks=26、passed=true** |
| 7. ctest | **169/169，0失败，退出码0，45.72秒** |

封面前置 CSS margin 是 **8.5px**；改前第一页为 **0 字形／0 图片框**。改后第一页图片 **y=8.5、高520.5、底边529.0**，缓存计费 **15,372,040**。该页像素 SHA-256：

`f788e74352073637227e0ebfa57391a1205003dcf7c4ae2474acf086cdcdfde2`

哈希定义沿用现有像素探针：三个小端 DWORD（width、height、channels），随后逐行有效 RGBA 字节，不含 stride padding。封面固定参数 **578×529 / margin0 / font17 / line1.6 / paragraph13.6 / Reader.otf**。本次 UI 实测窗口 DPI=120，注入 shell／D2D DPI=96，实际 client=1042×705；页面仍为 578×529、scale=1，详见 [首次布局](ui-first/first-cover.json) 和 [恢复布局](ui-restore/restored-cover.json)。

Sample 固定参数为 **800×1040 / margin36 / font28 / line1.5 / paragraph10 / Arial**；修改前后使用相同可执行探针和输入，唯一运行库差异为 `src/flow.c`。42 页全部前后哈希见 [SAMPLE-PAGES.csv](SAMPLE-PAGES.csv)。另以 720×1040 配置核对 **48→48 页、0/48 差异**。这两个配置分别记录，未将 720×1040 的48页报告成42页。

中文固定参考使用 `Reader.otf`、现有 `tools/probes/cjk_measure.c`，遍历31章；完整前后汇总见 [CJK-SUMMARY.json](CJK-SUMMARY.json)。

## 三项离屏 UI 实测

用户明确批准本轮三项离屏验收。宿主通过 `--offscreen` 在 **(-32000,-32000)** 创建窗口，使用 `WS_EX_NOACTIVATE` 和 `SW_SHOWNOACTIVATE`，所有快照只走 `PrintWindow(PW_RENDERFULLCONTENT)`；失败时不截桌面。运行脚本不含 activate/key_tab/probe_resize，不调用 SetForegroundWindow、BringWindowToTop 或移动鼠标。

| 场景 | 退出码 | 步骤 | 监测次数 | 前台观测 | 实际窗口左上角 | 截图尺寸 |
|---|---|---|---|---|---|---|
| 首次打开 | 0 | 17/17 | 62 | 0 | (-32000,-32000) | 1060×752 |
| 现有记录恢复 | 0 | 16/16 | 60 | 0 | (-32000,-32000) | 1060×752 |
| 8 MiB 故障 | 0 | 13/13 | 43 | 0 | (-32000,-32000) | 1060×752 |

三张 PrintWindow 截图均已逐一目视核对，首次打开与恢复截图的 SHA-256 相同。原始截图分别位于：

- `C:/Users/Oscar/Documents/Codex/cjk-host-open-fix-20261106/ui-first/first-cover.png`
- `C:/Users/Oscar/Documents/Codex/cjk-host-open-fix-20261106/ui-restore/restored-cover.png`
- `C:/Users/Oscar/Documents/Codex/cjk-host-open-fix-20261106/ui-fault/fault.png`

监测器 [run_offscreen.py](run_offscreen.py) 每 20ms 读取前台 PID 和目标窗口矩形，异常即结束该次验收；三个 [process.json](ui-first/process.json) 分别随场景保存命令、可执行文件哈希、坐标和观测次数。首次预检因监测器未启用 DPI awareness，将物理 -32000 读成虚拟 -25600，启动约 0.11 秒后被监测器终止，未执行验收步骤；随后仅将监测器设为 PMv2，再完成上述三项。预检日志保留在原始目录 `ui-first-dpi-virtualized/process.json`。

## 本地复现与来源

外部原始构建、程序、输入记录、全部日志与离屏脚本位于 `C:/Users/Oscar/Documents/Codex/cjk-host-open-fix-20261106/`。所有子进程使用 `CREATE_NO_WINDOW`。现有库只读备份到独立验证 profile，未修改原库。三项 UI 使用首次空库、现有记录副本、故障副本三个独立 profile；脚本及运行结果已复制到本证据目录。

最终构建与测试启用 OpenJPEG 2.5.4，关闭 AAC/MP3/PDF_CRYPTO/ICC/WebP/TIFF/AVIF/JNI，与前轮169项本地测试配置一致。基线通过 `git show HEAD:src/flow.c` 重建 DLL；`finally` 恢复最终源码，再完整构建、执行 ctest。输入和二进制 SHA-256 见 [PROVENANCE.json](PROVENANCE.json)。

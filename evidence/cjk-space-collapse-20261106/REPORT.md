# 中文正文空白折叠修复 — 2026-11-06

基线：main `c665d1cb1c0b681d4365f732acf775167bfa6d33`。正文汉字间空格 **16,243→0**；紅樓夢 **1,632→1,599 页**；Sample **42→42 页、像素 SHA-256 差异 0/42**；最终本地 **ctest 169/169 通过，40.64 秒**。

## 实现与改动行

| 文件 | 行 | 改动 |
|---|---:|---|
| `src/document.c` | 371–425 | 保存上一个 Unicode 字符；375 行共用 CJK 类别判定；387 行起 `project_text()` 按完整 UTF-8 字符投影，仅在空白左右均为 CJK 时丢弃待输出空格 |
| `src/document_internal.h` | 90 | 声明内部共用判定 |
| `src/chapter_index.c` | 23、193–225 | 流式章节索引使用同一判定及 UTF-8 字节长度，保持索引／窗口投影坐标一致 |
| `tests/test_construct.c` | 443–479 | `cjk_spaces()`、`mixed_spaces()` 两组、11 个用例、44 个新增断言；构造测试共 393 checks |
| `tests/test_chapter_index.c` | 71–72 | CJK／混合文本在 1、2、3、7、31、32768 字节输入块下与完整投影逐节点一致 |
| `tests/test_chapter_window.c` | 72 | CJK 空白跨注释节点；1、3、17、32768 字节回放窗口与完整快照一致 |
| `tests/test_line_boundary.c` | 276、325、356、364、432 | 保留原禁则／advance 断言，输入改为仍保留 SP 的混合文本、NBSP，并显式检查 SP 仍在 |
| `evidence/ci-packaging-20261103/R-PROTECTED-TREES.md` | 30 | 登记上述三个 src 受保护文件 |

ASCII SP/TAB/LF/CR 连续空白沿用待输出单空格逻辑，显式单个 SP 与源码硬折行适用同一类别规则，状态跨内联节点保留。类别覆盖 CJK 表意文字及扩展／兼容区、U+3000–303F 标点、竖排／兼容标点、全角符号；具体范围见共用函数。ASCII 标点、希腊字母、拉丁字母、ASCII 数字属于非 CJK。NBSP、源码全角缩进 U+3000 沿用原处理。

仅改完整投影时，真实宿主曾报 `Chapter window projection differs from index`：`src/chapter_index.c` 有独立计长逻辑。新增用例在未同步索引时均失败（索引 53 字节／快照 46 字节、窗口 EXR_FORMAT）；同步共用判定后通过。原始 DOM 文本和属性不修改，新增构造测试同时断言原文保留。

## 六项验收

| 项目 | 数字 |
|---|---|
| 1. 紅樓夢正文空格 | **汉字 SP 汉字 16,243→0**；包括标点／全角符号的 **CJK SP CJK 27,222→0**；遍历全部 **31 parts** |
| 2. 紅樓夢页数 | **1,632→1,599，减少 33 页**；字形 **821,108→793,886，减少 27,222**；列／行 **36,712→35,940**；两次 status=0 |
| 3. 拉丁 Sample | **42→42 页，0/42 像素哈希差异**；42 对完整 SHA-256 见 [SAMPLE-PAGES.csv](SAMPLE-PAGES.csv) |
| 4. 混合文本 | 指定三例 **3/3 通过**；含其它边界共 **11/11 用例通过** |
| 5. 单测与 ctest | 旧实现新增构造测试退出 **1**，修复后 **0、393 checks**；最终 **169/169，0 失败，40.64 秒**，见 [CTEST.txt](CTEST.txt) |
| 6. 同页截图 | **2/2 次离屏运行通过，各 12/12 步**；均 `part=15 / index=0`，client **1280×800**；前台观测均 **0**；窗口均 **(-32000,-32000)** |

页数减少来自正文空格被删除和重新分行，属于预期结果。中文测量沿用 `tools/probes/cjk_measure.c`，固定 **720×1040 / margin36 / font28 / line1.5 / paragraph10 / Reader.otf**，强制横排。统计见 [RESULTS.json](RESULTS.json)。

Sample 使用相同 `sample_probe.exe`、相同输入及 Arial 字体，固定 **800×1040 / margin36 / font28 / line1.5 / paragraph10**。像素哈希为小端 width、height、channels 三个 DWORD，后接每行有效 RGBA 字节，不含 stride padding。两个阶段探针可执行文件的 SHA-256 一致；运行库分别来自基线／最终实现。

三例的明确判定：

- `GPU 加速` → `GPU 加速`：左侧 U 为拉丁字母，保留 **1** 个 SP。
- `你 好` → `你好`：两侧都是汉字，保留 **0** 个 SP。
- `第一章 总论` → `第一章总论`：空格紧邻的左右字符是“章”和“总”，都属于 CJK，保留 **0** 个 SP。此规则不按章节标题语义保留分隔。

初次全量测试 **168/169**，旧 `native-line-boundary` 输入中的 CJK SP 被新规则删除，因此原“SP 前的边界”断言不再有原前提，日志见 [CTEST-INITIAL.txt](CTEST-INITIAL.txt)。更新输入后保留其所有边界／advance 断言，并显式要求混合文本 SP 仍存在。没有修改禁则或标点压缩实现。

## 统计方法与命令

统计 **SDK 实际投影**，不统计 XHTML 原始换行。`space_probe.c` 逐 part 调用 `exr_publication_load()`，从 `exr_document_blocks()` 中导出 `heading==0` 的正文块，各块用 LF 分隔；计数器只匹配两字符间的 **U+0020**，使用正向／反向零宽断言，避免 `你 好 吗` 漏计第二个空格。`body-*.txt` 原始正文保存在本地，不提交书籍全文。

以下 PowerShell 命令在仓库根目录运行；`before` 和 `after` 目录分别含基线及最终构建的 DLL／导入库：

```powershell
$spaceRaw = 'C:/Users/Oscar/Documents/Codex/cjk-space-collapse-20261106'
$spaceBook = 'C:/Users/Oscar/Documents/Codex/exr-cjk-corpus/hongloumeng-24264.epub'
foreach ($spacePhase in @('before','after')) {
  gcc -O2 -Wall -Wextra -Werror -I include evidence/cjk-space-collapse-20261106/space_probe.c -L "$spaceRaw/$spacePhase" -lexreader -o "$spaceRaw/$spacePhase/space_probe.exe"
  New-Item -ItemType Directory -Force "$spaceRaw/$spacePhase/text" | Out-Null
  & "$spaceRaw/$spacePhase/space_probe.exe" $spaceBook "$spaceRaw/$spacePhase/text"
}
python evidence/cjk-space-collapse-20261106/count_spaces.py "$spaceRaw/before/text" "$spaceRaw/after/text"
```

输出分别为 `parts=31, han_space_han=16243, cjk_space_cjk=27222` 和 `parts=31, han_space_han=0, cjk_space_cjk=0`。正文 U+0020 总数 **32,901→5,679**，其余空格符合任一侧非 CJK 的规则。

完整遍历、Sample 和本地全量测试的实际命令：

```powershell
& "$spaceRaw/before/cjk_measure.exe" $spaceBook 'C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Reader.otf' 0
& "$spaceRaw/after/cjk_measure.exe" $spaceBook 'C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Reader.otf' 0
& "$spaceRaw/before/sample_probe.exe" 'C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Sample.epub' C:/Windows/Fonts/arial.ttf
& "$spaceRaw/after/sample_probe.exe" 'C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Sample.epub' C:/Windows/Fonts/arial.ttf
ctest --test-dir C:/Users/Oscar/Documents/Codex/cjk-host-open-fix-20261106/build --output-on-failure -j 4
```

构建配置复用上一轮 JPX 开启的 169 项本地配置，依赖及完整 CMake 参数见 [上轮 PROVENANCE.json](../cjk-host-open-fix-20261106/PROVENANCE.json)。本轮输入／源码／二进制／截图哈希见 [PROVENANCE.json](PROVENANCE.json)。

## 同页截图与范围

使用原 P0 已定稿的同一个 `EXReader.exe`（SHA-256 `0e0d31592720ec6dc1fe8835cf8fb83b9422e7524f507c8e939d986c1070d0e0`），只为前后两份验证副本替换 SDK DLL。复用独立 profile 副本，将恢复记录定为原截图对应 `part=15 / position=0`。实际两次均进入阅读屏，截图已目视核对，“探 春”变为“探春”。

- [改前 clear-text-before-1280.png](../../docs/ui/evidence/2a-step5-art/clear-text-before-1280.png)
- [改后 clear-text-after-1280.png](../../docs/ui/evidence/2a-step5-art/clear-text-after-1280.png)

两次页面尺寸均 **612×624**，字号 **18**、margin **0**、line_height **1.6**、paragraph **14.400001**、mode **0**，重新分行后本页投影范围 **[0,1691]→[0,1774]**。完整 glyph／line 数组保存在对应 `clear-text-*.json`；进程记录见 [SCREENSHOTS.json](SCREENSHOTS.json)，驱动日志见 [UI-before.txt](UI-before.txt)、[UI-after.txt](UI-after.txt)。只用既有 `--offscreen` 与 PrintWindow，无前台窗口。

未改配色、圆角、间距、行高、夹具或工作流。所有构建／测量／验证子进程使用 CREATE_NO_WINDOW。未手动触发 CI，未取消 workflow run；提交信息不含 CI 跳过标记。

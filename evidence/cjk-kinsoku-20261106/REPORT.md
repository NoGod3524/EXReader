# 中文 SP 后冒号／分号禁则与探针修复 — 2026-11-06

基线 `24c12bcdaac897defdd330b7e264bd8215451f59`（main，SDK 3.42.0）。本地构建、测量和测试；未开窗口、未跑 CI。输入书籍、字体、二进制与完整 PAIR 输出留在仓库外。

## 根因与改动

`project_text()` 将源码普通换行折叠为 SP。默认 Unicode 分行按 LB18 先于 LB21 处理，SP 后的 NS 类全角冒号／分号可断；CL 类逗号此前已经受保护。紅樓夢三处 `道\n：`／`口\n：` 因此成为合法软断点。

`src/inline.c` 新增共用 `inline_boundary()`：仅在前一标量为 U+0020、当前为 U+FF1A/U+FF1B、边界非 MANDATORY 时清 LINE、置 GLUE。`exr_inline_feed()` 和 `display_scan()` 同时调用，既阻止普通断行，也阻止应急断行和显示重建恢复旧断点。`exr_text_analyze()` 及 LB21 顺序保持默认行为。

探针按中文惯例把 U+201C `“` 加入 `tail_bad`，U+201D `”` 加入 `head_bad`；集合语义不冲突，`punct()` 也随之覆盖两者。Windows 入口 include 改为仓库相对路径。

受保护树登记：**src/**，具体为 `src/inline.c`；已追加到 [R-PROTECTED-TREES.md](../ci-packaging-20261103/R-PROTECTED-TREES.md)。后续 R 候选须包含此修复。

## 1. 行首与相邻标点对

同一探针、同一本输入、同一 Reader.otf；参数 `0`。页配置 `{720,1040,36,28,1.5f,10}`，CSS `html,body{writing-mode:horizontal-tb!important}`。下表“原始行首异常”采用旧报告的统计口径，包含硬断冲突。

| 书 | 原始行首异常 改前→改后 | 旧探针 pairs | 修正探针／旧引擎 pairs | 修正探针／新引擎 pairs |
|---|---:|---:|---:|---:|
| 紅樓夢 | 4→1 | 54 | 15,166 | 15,170 |
| 醒世恆言 | 0→0 | 11,352 | 11,352 | 11,352 |
| 唐詩 | 0→0 | 0 | 0 | 0 |

旧探针／旧引擎重跑逐字段复现原报告。修正字符集后，紅樓夢大量 `：“`、`。”` 等进入 PAIR；引擎修复后的重新分行又使同行 `：“` 对净增 4（新增 13、移出同行 9）。醒世恆言以 `「」` 为主，原探针已覆盖，新增字符未增加符合 PAIR 全部条件的对；唐詩仍无符合条件的对。PAIR 依然要求同行、源 cluster 相邻、同字体同字号且同行有汉字 advance 参照。

新字符集另揭示紅樓夢 **2 处既有行尾左引号**：p635/part13/source_start18739、p638/part13/source_start23032。两处都是 `“` 后接折叠空格；修正探针测旧／新引擎均为 2，旧探针漏报为 0。本次引擎过滤仅涉及 SP 后全角冒号／分号。另两本 tail 均为 0。

## 2. 行首异常分类与仍无解的一处

`head_observations` 保留旧口径；`head_violations` 只计 `soft_wrap`，其余三类单列，互斥且四类合计等于 observations。这样旧口径的 **4→1** 与修复后 `head_violations=0` 可以同时核对，不把结构性硬断冲突混入可修复违规数。

| 书／阶段 | head_observations | head_violations / soft_wrap | forced_break | paragraph_start | unbreakable_overflow |
|---|---:|---:|---:|---:|---:|
| 紅樓夢／改前 | 4 | 3 | 1 | 0 | 0 |
| 紅樓夢／改后 | 1 | 0 | 1 | 0 | 0 |
| 醒世恆言／改前及改后 | 0 | 0 | 0 | 0 | 0 |
| 唐詩／改前及改后 | 0 | 0 | 0 | 0 | 0 |

探针用公开 document blocks/nodes 与 MANDATORY 边界识别段首和 `<br/>`；overflow 类要求观测行跨度超过配置内容区且首字边界为 GLUE。分类不依据行中有无汉字。每个 head EDGE 增加 `reason`。

仍无解处：**紅樓夢 p1033，part=20，source_start=32144，U+FF0C**，原文件 `OEBPS/2878037014660817796_24264-0-21.txt.html` 的 `p#id00318`：

```html
《九辯》，《枯樹》，《問難》<br/>
，《秋水》，<br/>
《大人先生傳》等法……
```

保留 `<br/>` 时，软断行无法把首逗号搬回前行；书源须把逗号移到前一个 `<br/>` 前或删除误插硬换行。此次保留原书和硬断结构，单独计 `forced_break=1`。

## 3. Pachinko 非 CJK 回归

葡萄牙语 Pachinko、Arial、既有 `alias_page_probe.c`，沿用 `check_document` 的页面配置与调用方式：

- 页数 **1,194→1,194**；本轮改前／改后逐页像素哈希不同数 **0/1,194**。
- 与此前 `css-alias-20261105/after-pachinko.json` 的 1,194 个哈希比较，不同数也为 **0/1,194**。
- SHA-256 输入为小端 DWORD width/height/channels，再按行拼接有效 RGBA 像素（不含 stride padding）。
- [PACHINKO-PAGES.csv](PACHINKO-PAGES.csv) 保存逐页改前／改后哈希；输入和工具 SHA-256 见 [PROVENANCE.json](PROVENANCE.json)。

## 4. 中文分页与测试

| 书 | 改前页数 | 改后页数 | 改前行数 | 改后行数 |
|---|---:|---:|---:|---:|
| 紅樓夢 | 1,652 | 1,652 | 37,154 | 37,155 |
| 醒世恆言 | 1,170 | 1,170 | 26,510 | 26,510 |
| 唐詩 | 86 | 86 | 1,786 | 1,786 |

断行调整会改变后续行分配，可能改变页数，属于预期重排。本次紅樓夢增加 1 行，三本总页数恰好均未改变；断行改变不必然改变总页数。三本字形数分别保持 821,108／562,814／50,095，wrong_mode_pages 和 status 全为 0。[RESULTS.csv](RESULTS.csv) 保存修正探针测旧／新引擎的六行完整汇总。

相关本地 **ctest 13/13 通过**：text、line-boundary、hyphen、hyphen-replacements、hyphen-layout、pager、page-cache、flow、vertical、shaping、bidi、complex-layout、checkpoints。日志见 [CTEST.txt](CTEST.txt)。没有既有测试断言旧行为而失败，也没有修改既有断言。

新增测试覆盖 U+FF1A/U+FF1B、跨 inline 节点、普通／应急断行、显示替换引入的 SP+标点、默认分析接口和其他 NS 字符不变、硬换行与段首保留、分页／缓存像素一致性。分别临时移除 feed 和 display 过滤，native-line-boundary 均失败；恢复后通过。

独立 `test_cjk_probe.c` 自检通过：左右引号集合、相邻标点识别及四类行首原因。构建示例（`<sdk>` 含同版本库及 DLL）：

```text
gcc -O2 -Wall -Wextra -Werror -I include tools/probes/cjk_measure.c -L <sdk> -lexreader -lm -o <sdk>/cjk_measure.exe
gcc -O2 -Wall -Wextra -Werror -I include tests/test_cjk_probe.c -L <sdk> -lexreader -lm -o <sdk>/test_cjk_probe.exe
<sdk>/test_cjk_probe.exe
<sdk>/cjk_measure.exe <book.epub> <Reader.otf> 0
ctest --test-dir <build> -R "^native-(line-boundary|text|hyphen|hyphen-replacements|hyphen-layout|pager|page-cache|flow|vertical|shaping|bidi|complex-layout|checkpoints)$" --output-on-failure -j 4
```

完整 CMake 配置与源文件、输入、工具、原始输出哈希保存于 PROVENANCE.json。测量进程用 CREATE_NO_WINDOW 启动。提交使用 `[skip ci]`，用于遵守本次不跑 CI 的要求。

<!-- ci trigger 2026-11-06 -->
